import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('news', Path(__file__).resolve().parents[1] / 'scripts/update_readme.py')
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)
README = '''# Louis Kim
[Company Lens 코드](https://github.com/ersione/company-lens)
<!-- releases:start -->
old release
<!-- releases:end -->
Keep these project cards.
<!-- posts:start -->
old post
<!-- posts:end -->
Footer
'''
RELEASE = {
    'id': 'ersione-design-system@v0.5.1', 'repository': 'ersione-design-system',
    'title': 'Ersione Design System', 'version': 'v0.5.1',
    'url': 'https://github.com/ersione/ersione-design-system/releases/tag/v0.5.1',
    'badgeUrl': '/api/profile/release/ersione-design-system.svg?version=v0.5.1',
    'publishedAt': '2026-10-14T16:10:38Z', 'alt': '정식 릴리스 v0.5.1',
}
POST = {'id': 'https://blog.ersione.com/example', 'url': 'https://blog.ersione.com/example', 'title': 'A [title] <b>', 'publishedAt': '2026-03-01T00:00:00Z'}
DATA = {'schemaVersion': 1, 'status': 'ready', 'releases': {'status': 'ready', 'items': [RELEASE]}, 'posts': {'status': 'ready', 'items': [POST]}}
BADGE = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="28" data-version="v0.5.1"><title>release</title><path d="M0 0"/></svg>'


def loader(data=DATA, badge=BADGE):
    def load(url, mime):
        return json.dumps(data).encode() if mime == 'application/json' else badge
    return load


class NewsTests(unittest.TestCase):
    def test_snapshot_updates_links_and_content_addressed_badge(self):
        updated, assets = news.prepare(README, 'https://ersione.com', loader())
        self.assertIn('[Ersione Design System]', updated)
        self.assertIn('![정식 릴리스 v0.5.1](assets/news/release-', updated)
        self.assertIn('A \\[title\\] &lt;b&gt;', updated)
        self.assertIn('· 2026-03-01', updated)
        self.assertIn('[Company Lens 코드](https://github.com/ersione/company-lens)', updated)
        self.assertIn('Keep these project cards.', updated)
        self.assertEqual(list(assets.values()), [BADGE])
        self.assertEqual(news.prepare(updated, 'https://ersione.com', loader()), (updated, assets))

    def test_success_then_identical_data_performs_no_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            path.write_text(README)
            self.assertTrue(news.refresh_file(path, 'https://ersione.com', loader()))
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(directory).rglob('*') if p.is_file()}
            self.assertFalse(news.refresh_file(path, 'https://ersione.com', loader()))
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_failure_preserves_all_sections_and_assets(self):
        failures = [lambda *_: (_ for _ in ()).throw(TimeoutError()), loader(data={**DATA, 'status': 'unavailable'}), loader(badge=b'<svg>broken'), loader(badge=BADGE.replace(b'v0.5.1', b'v0.5.2'))]
        for failed in failures:
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'README.md'
                path.write_text(README)
                before = path.stat().st_mtime_ns
                with self.assertRaises(Exception):
                    news.refresh_file(path, 'https://ersione.com', failed)
                self.assertEqual(path.read_text(), README)
                self.assertEqual(path.stat().st_mtime_ns, before)
                self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_partial_stale_empty_and_bad_schema_cannot_erase_previous_news(self):
        for mutate in [lambda d: d.update(schemaVersion=2), lambda d: d['posts'].update(status='stale'), lambda d: d['releases'].update(items=[]), lambda d: d['posts'].update(items=[]), lambda d: d['posts']['items'][0].update(publishedAt='2099-01-01T00:00:00Z')]:
            data = copy.deepcopy(DATA)
            mutate(data)
            with self.assertRaises(ValueError):
                news.prepare(README, 'https://ersione.com', loader(data))

    def test_malformed_or_nested_markers_never_fetch(self):
        malformed = [README.replace('<!-- posts:end -->', ''), README + '<!-- releases:start -->', '<!-- releases:start --><!-- posts:start --><!-- releases:end --><!-- posts:end -->']
        for value in malformed:
            with patch.object(news, 'fetch') as fetch, self.assertRaises(ValueError):
                news.prepare(value, 'https://ersione.com', fetch)
            fetch.assert_not_called()

    def test_svg_is_restricted_to_local_shapes_and_matching_version(self):
        malicious = [b'<!DOCTYPE svg>' + BADGE, BADGE.replace(b'<path', b'<script'), BADGE.replace(b'<path', b'<image href="https://evil.example/x"'), BADGE.replace(b'<path', b'<path onload="alert(1)"'), BADGE.replace(b'<path', b'<path fill="url(https://evil.example)"')]
        for body in malicious:
            with self.assertRaises((ValueError, news.ET.ParseError)):
                news.validate_svg(body, 'v0.5.1')

    def test_untrusted_links_versions_and_duplicates_are_rejected(self):
        mutations = [lambda d: d['posts']['items'][0].update(url='javascript:alert(1)'), lambda d: d['releases']['items'][0].update(badgeUrl='https://evil.example/badge.svg'), lambda d: d['releases']['items'][0].update(badgeUrl='/api/profile/release/ersione-design-system.svg?version=other'), lambda d: d['releases']['items'][0].update(repository='../private'), lambda d: d['posts']['items'].append(copy.deepcopy(d['posts']['items'][0]))]
        for mutate in mutations:
            data = copy.deepcopy(DATA)
            mutate(data)
            with self.assertRaises(ValueError):
                news.prepare(README, 'https://ersione.com', loader(data))

    def test_dry_run_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            path.write_text(README)
            self.assertTrue(news.refresh_file(path, 'https://ersione.com', loader(), dry_run=True))
            self.assertEqual(path.read_text(), README)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_api_origin_local_opt_in_and_no_redirect(self):
        self.assertEqual(news.api_base('https://ersione.com/'), 'https://ersione.com')
        self.assertEqual(news.api_base('http://127.0.0.1:3017', True), 'http://127.0.0.1:3017')
        for value in ['https://evil.example', 'http://ersione.com', 'https://user@ersione.com', 'http://127.0.0.1:3017']:
            with self.assertRaises(ValueError):
                news.api_base(value)
        with self.assertRaises(news.HTTPError) as caught:
            news.NoRedirect().redirect_request(news.Request('https://ersione.com'), None, 302, '', {}, 'https://evil.example')
        caught.exception.close()


if __name__ == '__main__':
    unittest.main()
