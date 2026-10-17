import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('news', Path(__file__).resolve().parents[1] / 'scripts/update_readme.py')
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)
README = '''# Personal intro
<!-- releases:start -->
old release
<!-- releases:end -->
Keep this project list.
<!-- posts:start -->
old post
<!-- posts:end -->
Footer
'''


class NewsTests(unittest.TestCase):
    def test_failure_preserves_one_source_and_manual_content(self):
        with patch.object(news, 'recent_releases', side_effect=TimeoutError), patch.object(news, 'recent_posts', return_value='new post'):
            updated, failed = news.refresh(README)
        self.assertEqual(updated, README.replace('old post', 'new post'))
        self.assertEqual(failed, ['releases'])

    def test_unchanged_content_is_idempotent(self):
        with patch.object(news, 'recent_releases', return_value='old release'), patch.object(news, 'recent_posts', return_value='old post'):
            self.assertEqual(news.refresh(README), (README, []))

    def test_invalid_boundaries_never_fetch(self):
        for malformed in (README.replace('<!-- posts:end -->', ''), README + '<!-- releases:start -->', README.replace('<!-- posts:start -->', '<!-- temp -->').replace('<!-- posts:end -->', '<!-- posts:start -->').replace('<!-- temp -->', '<!-- posts:end -->')):
            with patch.object(news, 'recent_posts') as fetch, self.assertRaises(ValueError):
                news.refresh(malformed)
            fetch.assert_not_called()

    def test_posts_are_sorted_and_future_items_excluded(self):
        rss = b'''<rss><channel>
        <item><title>Future</title><link>https://blog.ersione.com/future</link><pubDate>Thu, 01 Jan 2099 00:00:00 GMT</pubDate></item>
        <item><title>Old</title><link>https://blog.ersione.com/old</link><pubDate>Wed, 01 Jan 2020 00:00:00 GMT</pubDate></item>
        <item><title>New</title><link>https://blog.ersione.com/new</link><pubDate>Fri, 01 Jan 2021 00:00:00 GMT</pubDate></item>
        </channel></rss>'''
        with patch.object(news, 'fetch', return_value=rss):
            self.assertEqual(news.recent_posts().splitlines(), ['- [New](<https://blog.ersione.com/new>)', '- [Old](<https://blog.ersione.com/old>)'])

    def test_releases_exclude_drafts_and_prereleases(self):
        data = [dict(tag_name='v1', html_url='https://github.com/ersione/ersione-design-system/releases/tag/v1', published_at='2020-01-01T00:00:00Z'), dict(draft=True), dict(prerelease=True)]
        with patch.dict(news.REPOSITORIES, {'ersione-design-system': 'Design System'}, clear=True), patch.object(news, 'fetch', return_value=json.dumps(data).encode()):
            self.assertEqual(news.recent_releases(), '- [Design System · v1](<https://github.com/ersione/ersione-design-system/releases/tag/v1>)')

    def test_bad_and_empty_sources_keep_previous_news(self):
        for response in (b'bad xml or json', b'<rss><channel/></rss>', b'[]'):
            with patch.object(news, 'fetch', return_value=response):
                updated, failed = news.refresh(README)
            self.assertEqual(updated, README)
            self.assertEqual(failed, ['releases', 'posts'])

    def test_unsafe_links_are_rejected_and_titles_escaped(self):
        for url in ('http://blog.ersione.com/a', 'https://evil.example/a', 'https://user@blog.ersione.com/a', 'https://blog.ersione.com/a>'):
            with self.assertRaises(ValueError):
                news.link('title', url, 'blog.ersione.com')
        self.assertEqual(news.link('[text] <b>', 'https://blog.ersione.com/a', 'blog.ersione.com'), '- [\\[text\\] &lt;b&gt;](<https://blog.ersione.com/a>)')

    def test_github_token_does_not_go_to_blog(self):
        with patch.dict(news.os.environ, {'GITHUB_TOKEN': 'test-token'}), patch.object(news, 'urlopen') as request:
            news.fetch('https://blog.ersione.com/rss.xml')
            self.assertIsNone(request.call_args.args[0].get_header('Authorization'))
            news.fetch('https://api.github.com/repos/ersione/ersione/releases')
            self.assertEqual(request.call_args.args[0].get_header('Authorization'), 'Bearer test-token')


if __name__ == '__main__':
    unittest.main()
