"""RSS news gateway: config-only sources, RSS/RDF/Atom parsing, safety checks."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from plugins_func.functions import get_news_rss as news

NOW = datetime.now(timezone.utc)
RFC822 = "%a, %d %b %Y %H:%M:%S +0000"

RSS2 = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>A</title>
<item><title>Fresh &amp; new</title><link>https://a.example/1</link>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
<pubDate>{NOW.strftime(RFC822)}</pubDate></item>
<item><title>Old story</title><link>https://a.example/old</link>
<pubDate>{(NOW - timedelta(days=30)).strftime(RFC822)}</pubDate></item>
<item><title>Duplicate</title><link>https://shared.example/x</link></item>
</channel></rss>""".encode()

RDF = f"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<item><title>RDF item about AI</title><link>https://b.example/1</link>
<description>AI summary</description><dc:date>{(NOW - timedelta(hours=1)).isoformat()}</dc:date></item>
<item><title>Duplicate</title><link>https://shared.example/x</link></item>
</rdf:RDF>""".encode()

ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom entry</title><link rel="alternate" href="https://c.example/1"/>
<summary>Atom summary</summary><updated>{(NOW - timedelta(hours=2)).isoformat()}</updated></entry>
</feed>""".encode()

BOMB = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><rss><channel><item><title>&lol;</title></item></channel></rss>"""

FEEDS = (
    "Alpha|https://a.example/rss|en|world;"
    "Beta|https://b.example/rdf|zh|tech;"
    "Gamma|https://c.example/atom|en|world"
)


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class FakeClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.urls = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.urls.append(url)
        value = self.mapping[url]
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value)


def conn(settings):
    return SimpleNamespace(config={"plugins": {"get_news_rss": settings}})


class ParseTests(unittest.TestCase):
    def test_parse_feeds_string_list_and_rejects_non_https(self):
        feeds = news.parse_feeds("A|https://a.example/rss|EN|World, Tech\nB|http://insecure.example/rss;C|ftp://x;broken")
        self.assertEqual([f["name"] for f in feeds], ["A"])
        self.assertEqual(feeds[0]["language"], "en")
        self.assertEqual(feeds[0]["topics"], ["world", "tech"])
        feeds = news.parse_feeds([{"name": "D", "url": "https://d.example/rss", "topics": "x,y"}])
        self.assertEqual(feeds[0]["topics"], ["x", "y"])
        self.assertEqual(news.parse_feeds(None), [])

    def test_parse_rss_rdf_atom(self):
        rss = news.parse_feed_xml(RSS2, "Alpha")
        self.assertEqual(rss[0]["title"], "Fresh & new")
        self.assertEqual(rss[0]["summary"], "Hello world")
        self.assertIsNotNone(rss[0]["published"])
        rdf = news.parse_feed_xml(RDF, "Beta")
        self.assertEqual(rdf[0]["link"], "https://b.example/1")
        self.assertIsNotNone(rdf[0]["published"])
        atom = news.parse_feed_xml(ATOM, "Gamma")
        self.assertEqual(atom[0]["link"], "https://c.example/1")

    def test_rejects_entity_declarations(self):
        with self.assertRaises(ValueError):
            news.parse_feed_xml(BOMB, "Bad")


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        news._feed_cache.clear()

    async def test_no_feeds_configured_means_no_network(self):
        client = FakeClient({})
        with patch.object(news.httpx, "AsyncClient", client):
            result = await news.get_news_rss(conn({}))
        self.assertIn("尚未設定", result.result)
        self.assertEqual(client.urls, [])

    async def test_merges_dedupes_filters_age_and_sorts(self):
        client = FakeClient({
            "https://a.example/rss": RSS2,
            "https://b.example/rdf": RDF,
            "https://c.example/atom": ATOM,
        })
        c = conn({"feeds": FEEDS, "max_items": 10})
        with patch.object(news.httpx, "AsyncClient", client):
            result = await news.get_news_rss(c)
        text = result.result
        self.assertNotIn("Old story", text)
        self.assertEqual(text.count("Duplicate"), 1)
        self.assertLess(text.index("Fresh & new"), text.index("RDF item about AI"))
        self.assertLess(text.index("RDF item about AI"), text.index("Atom entry"))
        self.assertTrue(c.last_news_rss_items)

    async def test_unknown_source_lists_available(self):
        with patch.object(news.httpx, "AsyncClient", FakeClient({})):
            result = await news.get_news_rss(conn({"feeds": FEEDS}), source="澎湃新聞")
        self.assertIn("Alpha", result.result)
        self.assertIn("沒有設定", result.result)

    async def test_language_selects_feeds(self):
        client = FakeClient({"https://b.example/rdf": RDF})
        with patch.object(news.httpx, "AsyncClient", client):
            await news.get_news_rss(conn({"feeds": FEEDS}), language="zh_TW")
        self.assertEqual(client.urls, ["https://b.example/rdf"])

    async def test_failed_feed_is_reported_others_still_returned(self):
        client = FakeClient({
            "https://a.example/rss": RuntimeError("down"),
            "https://b.example/rdf": RDF,
            "https://c.example/atom": ATOM,
        })
        with patch.object(news.httpx, "AsyncClient", client):
            result = await news.get_news_rss(conn({"feeds": FEEDS}))
        self.assertIn("Atom entry", result.result)
        self.assertIn("Alpha", result.result)

    async def test_detail_uses_last_listing_only(self):
        c = conn({"feeds": FEEDS})
        result = await news.get_news_rss(c, detail=True)
        self.assertIn("先列出", result.result)
        client = FakeClient({"https://b.example/rdf": RDF})
        with patch.object(news.httpx, "AsyncClient", client):
            await news.get_news_rss(c, source="Beta")
            result = await news.get_news_rss(c, detail=True, index=1)
        self.assertIn("AI summary", result.result)
        self.assertEqual(len(client.urls), 1)


if __name__ == "__main__":
    unittest.main()
