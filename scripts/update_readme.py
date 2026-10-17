"""Read the profile API and atomically refresh only marked README news sections."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {'ersione-design-system', 'ersione-studio', 'company-lens'}
MAX_BYTES = 256 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise HTTPError(request.full_url, code, 'Redirect refused', headers, response)


def api_base(value, allow_local=False):
    parsed = urlsplit(value)
    remote = parsed.scheme == 'https' and parsed.netloc == 'ersione.com'
    local = allow_local and parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}
    if not (remote or local) or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise ValueError('Unexpected profile API origin')
    return value.rstrip('/')


def fetch(url, mime):
    # No token, cookies or authorization headers are sent to the profile API.
    request = Request(url, headers={'User-Agent': 'ersione-profile-readme', 'Accept': mime})
    with build_opener(NoRedirect).open(request, timeout=20) as response:
        if response.headers.get_content_type() != mime:
            raise ValueError('Unexpected response MIME')
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Response too large')
        return body


def source_url(value, host, prefix='/'):
    if not isinstance(value, str):
        raise ValueError('Invalid source URL')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc != host or not parsed.path.startswith(prefix) or parsed.fragment or re.search(r'[<>\s]', value):
        raise ValueError('Unexpected source URL')
    return value


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError('Invalid title')
    escaped = html.escape(' '.join(value.split()), quote=False)
    return re.sub(r'([\\\[\]`*_!])', r'\\\1', escaped)


def date(value):
    if not isinstance(value, str):
        raise ValueError('Missing publication date')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise ValueError('Invalid publication date')
    return parsed.date().isoformat()


def replace_sections(original, releases, posts):
    result = original
    # Validate every boundary before performing any replacement.
    for name in ('releases', 'posts'):
        start, end = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
        if original.count(start) != 1 or original.count(end) != 1 or original.index(start) >= original.index(end):
            raise ValueError('Invalid README boundaries')
    starts = [original.index(f'<!-- {name}:start -->') for name in ('releases', 'posts')]
    ends = [original.index(f'<!-- {name}:end -->') for name in ('releases', 'posts')]
    if not (ends[0] < starts[1] or ends[1] < starts[0]):
        raise ValueError('Overlapping README sections')
    for name, content in (('releases', releases), ('posts', posts)):
        start, end = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
        before, rest = result.split(start)
        _, after = rest.split(end)
        result = f'{before}{start}\n{content}\n{end}{after}'
    return result


def prepare(original, base, loader=fetch):
    replace_sections(original, '', '')  # Refuse malformed README before networking.
    data = json.loads(loader(base + '/api/profile/news', 'application/json'))
    if data.get('schemaVersion') != 1 or data.get('status') != 'ready':
        raise ValueError('Profile API is not ready')
    release_lines, post_lines = [], []
    for name in ('releases', 'posts'):
        section = data.get(name, {})
        if section.get('status') != 'ready' or not isinstance(section.get('items'), list) or not 1 <= len(section['items']) <= 2:
            raise ValueError('Missing complete news section')
    ids = set()
    for item in data['releases']['items']:
        repo, version = item['repository'], item['version']
        if repo not in REPOSITORIES or not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,99}', version):
            raise ValueError('Invalid release identity')
        identity = f'{repo}@{version}'
        if item.get('id') != identity or identity in ids:
            raise ValueError('Duplicate or inconsistent release')
        ids.add(identity)
        url = source_url(item['url'], 'github.com', f'/ersione/{repo}/releases/tag/')
        published, label = date(item['publishedAt']), title(item['title'])
        badge = 'https://img.shields.io/static/v1?' + urlencode({
            'label': 'release', 'message': version, 'color': '6b7280',
            'labelColor': '555', 'style': 'flat',
        })
        release_lines.append(f'- [{label}](<{url}>) [![release {version}]({badge})](<{url}>) · {published}')
    ids = set()
    for item in data['posts']['items']:
        url = source_url(item['url'], 'blog.ersione.com')
        if item.get('id') != url or url in ids:
            raise ValueError('Duplicate or inconsistent post')
        ids.add(url)
        post_lines.append(f"- [{title(item['title'])}](<{url}>) · {date(item['publishedAt'])}")
    return replace_sections(original, '\n'.join(release_lines), '\n'.join(post_lines))


def atomic_write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as output:
            temporary = Path(output.name)
            output.write(body)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def refresh_file(path, base, loader=fetch, dry_run=False):
    original = path.read_bytes()
    updated = prepare(original.decode('utf-8'), base, loader)
    encoded = updated.encode('utf-8')
    changed = encoded != original
    if not dry_run and changed:
        atomic_write(path, encoded)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readme', type=Path, default=ROOT / 'README.md')
    parser.add_argument('--api-base', default='https://ersione.com')
    parser.add_argument('--allow-local', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        changed = refresh_file(args.readme, api_base(args.api_base, args.allow_local), dry_run=args.dry_run)
    except Exception as error:
        # Avoid printing remote bodies, credentials or untrusted error messages.
        print(f'Keeping existing README news: {type(error).__name__}', file=sys.stderr)
        return 1
    print(('Would update' if args.dry_run else 'Updated') + ' profile news' if changed else 'No profile news changes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
