"""Missing tool configuration must not contact implicit (Chinese) cloud services."""
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from plugins_func.functions import get_news_from_chinanews as rss_news
from plugins_func.functions import get_news_from_newsnow as newsnow
from plugins_func.functions import web_search as search
from plugins_func.register import Action
from core.providers.tools.server_plugins.plugin_executor import ServerPluginExecutor


def connection(tool, settings=None) -> Any:
    return SimpleNamespace(config={"plugins": {tool: settings or {}}}, client_ip=None)


class CloudFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_rss_news_requires_configured_url(self):
        with patch.object(rss_news, "fetch_news_from_rss", new_callable=AsyncMock, return_value=[]) as fetch:
            result = await rss_news.get_news_from_chinanews(connection("get_news_from_chinanews"))
            self.assertIn("未配置", result.result)
            fetch.assert_not_awaited()
            await rss_news.get_news_from_chinanews(
                connection("get_news_from_chinanews", {"society_rss_url": "https://example.org/feed"}),
                category="社会",
            )
            fetch.assert_awaited_once_with("https://example.org/feed")

    async def test_newsnow_missing_config_or_unknown_source_never_fetches(self):
        with patch.object(newsnow, "fetch_news_from_api", new_callable=AsyncMock) as fetch:
            for settings in ({}, {"url": "https://example.org/?id="}, {"news_sources": "Hacker News"}):
                result = await newsnow.get_news_from_newsnow(connection("get_news_from_newsnow", settings))
                self.assertIn("未配置", result.result)
            configured = connection(
                "get_news_from_newsnow", {"url": "https://example.org/?id=", "news_sources": "Hacker News"}
            )
            result = await newsnow.get_news_from_newsnow(configured, source="澎湃新闻")
            self.assertIn("未配置或不受支持", result.result)
            fetch.assert_not_awaited()

    async def test_newsnow_defaults_to_first_configured_source_not_chinese_source(self):
        configured = connection(
            "get_news_from_newsnow", {"url": "https://example.org/?id=", "news_sources": "Hacker News;澎湃新闻"}
        )
        with patch.object(newsnow, "fetch_news_from_api", new_callable=AsyncMock, return_value=[]) as fetch:
            await newsnow.get_news_from_newsnow(configured)
            fetch.assert_awaited_once_with(configured, "hackernews")

    async def test_newsnow_api_requires_explicit_url(self):
        with patch.object(newsnow.httpx, "AsyncClient") as client:
            result = await newsnow.fetch_news_from_api(connection("get_news_from_newsnow"), "hackernews")
            self.assertEqual(result, [])
            client.assert_not_called()

    async def test_search_rejects_missing_unknown_or_legacy_metaso_provider(self):
        self.assertNotIn("metaso", search.SEARCH_PROVIDERS)
        self.assertFalse(hasattr(search, "_search_metaso"))
        with patch.object(search.httpx, "AsyncClient") as client:
            for provider in ("", "metaso", "bing-cn"):
                result = await search.web_search(
                    connection("web_search", {"provider": provider, "api_key": "key"}), "Paris"
                )
                self.assertEqual(result.action, Action.REQLLM)
                self.assertIn("搜索源无效", result.result)
            client.assert_not_called()

    async def test_search_dispatches_only_allowlisted_provider(self):
        with patch.object(search, "_search_tavily", new_callable=AsyncMock, return_value="ok") as tavily:
            result = await search.web_search(
                connection("web_search", {"provider": "Tavily", "api_key": "tvly-x"}), "Paris"
            )
            tavily.assert_awaited_once()
            self.assertEqual(result.result, "ok")

    async def test_news_description_has_no_implicit_chinese_sources(self):
        description = {"function": {"parameters": {"properties": {"source": {}}}}}
        plugin = SimpleNamespace(description=description)
        ServerPluginExecutor(connection("get_news_from_newsnow"))._init_news_source_description(
            plugin, "get_news_from_newsnow"
        )
        self.assertIn("未配置", description["function"]["parameters"]["properties"]["source"]["description"])
        self.assertNotIn("澎湃", str(description))

    async def test_rss_description_lists_configured_feeds_without_mutating_shared_schema(self):
        shared = {"function": {"parameters": {"properties": {"source": {"description": "orig"}}}}}
        executor = ServerPluginExecutor(
            connection("get_news_rss", {"feeds": "Example|https://example.org/rss.xml|en"})
        )
        result = executor._rss_news_description(shared)
        self.assertIn("Example", result["function"]["parameters"]["properties"]["source"]["description"])
        self.assertEqual(shared["function"]["parameters"]["properties"]["source"]["description"], "orig")


if __name__ == "__main__":
    unittest.main()
