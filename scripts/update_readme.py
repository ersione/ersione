"""Refresh only the public blog and release sections of the profile README."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {
    'ersione-design-system': 'Ersione Design System',
    'ersione-studio': 'Ersione’s Studio',
    'company-lens': 'Company Lens',
}


def fetch(url):
    headers = {'User-Agent': 'ersione-profile-readme'}
    # The RSS host must never receive the GitHub token.
    if urlsplit(url).hostname == 'api.github.com':
        headers['Accept'] = 'application/vnd.github+json'
        if token := os.environ.get('GITHUB_TOKEN'):
            headers['Authorization'] = f'Bearer {token}'
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        return response.read()


def link(title, url, host):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != host or parsed.username or parsed.password:
        raise ValueError('Unexpected source link')
    if any(c in url for c in '<>\r\n'):
        raise ValueError('Invalid link characters')
    title = html.escape(' '.join(title.split()), quote=False)
    title = re.sub(r'([\\\[\]`*_])', r'\\\1', title)
    if not title:
        raise ValueError('Empty source title')
    return f'- [{title}](<{url}>)'


def recent_posts():
    root = ET.fromstring(fetch('https://blog.ersione.com/rss.xml'))
    items = []
    now = datetime.now(timezone.utc)
    for item in root.findall('./channel/item'):
        date = parsedate_to_datetime(item.findtext('pubDate', ''))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if date <= now:
            items.append((date, link(item.findtext('title', ''), item.findtext('link', ''), 'blog.ersione.com')))
    items.sort(key=lambda item: item[0], reverse=True)
    if not items:
        raise ValueError('No published RSS items')
    return '\n'.join(text for _, text in items[:2])


def recent_releases():
    items = []
    for repo, name in REPOSITORIES.items():
        data = json.loads(fetch(f'https://api.github.com/repos/ersione/{repo}/releases?per_page=10'))
        if not isinstance(data, list):
            raise ValueError('Unexpected GitHub response')
        for release in data:
            if release.get('draft') or release.get('prerelease'):
                continue
            url = release['html_url']
            if not url.startswith(f'https://github.com/ersione/{repo}/releases/tag/'):
                raise ValueError('Unexpected release link')
            date = datetime.fromisoformat(release['published_at'].replace('Z', '+00:00'))
            if date <= datetime.now(timezone.utc):
                items.append((date, link(f"{name} · {release['tag_name']}", url, 'github.com')))
    items.sort(key=lambda item: item[0], reverse=True)
    if not items:
        raise ValueError('No public stable releases')
    return '\n'.join(text for _, text in items[:2])


def replace_section(readme, name, content):
    start, end = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
    before, rest = readme.split(start)
    _, after = rest.split(end)
    return f'{before}{start}\n{content}\n{end}{after}'


def refresh(readme):
    failed = []
    for name in ('releases', 'posts'):
        start, end = f'<!-- {name}:start -->', f'<!-- {name}:end -->'
        if readme.count(start) != 1 or readme.count(end) != 1 or readme.index(start) >= readme.index(end):
            raise ValueError(f'Invalid {name} boundaries')
    for name, loader in (('releases', recent_releases), ('posts', recent_posts)):
        try:
            content = loader()
        except Exception as error:
            failed.append(name)
            print(f'Keeping existing {name}: {type(error).__name__}', file=sys.stderr)
        else:
            readme = replace_section(readme, name, content)
    return readme, failed


def main():
    path = ROOT / 'README.md'
    original = path.read_text(encoding='utf-8')
    updated, failed = refresh(original)
    if updated != original:
        temporary = path.with_suffix('.md.tmp')
        temporary.write_text(updated, encoding='utf-8')
        temporary.replace(path)
        print('Updated public profile news')
    else:
        print('No profile news changes')
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
