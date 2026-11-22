"""Source-link coverage for the configured web-search providers."""
import unittest
from unittest.mock import patch

from plugins_func.functions import web_search as web_search_module


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        return FakeResponse(self.payload)

    async def get(self, *args, **kwargs):
        return FakeResponse(self.payload)


class WebSearchSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_tavily_includes_source_url(self):
        await self._assert_source_url(
            "_search_tavily",
            {"answer": "Answer", "results": [{"title": "Example", "content": "Summary", "url": "https://example.org/b"}]},
            "https://example.org/b",
        )

    async def test_serply_includes_source_url(self):
        await self._assert_source_url(
            "_search_serply",
            {"results": [{"title": "Example", "description": "Summary", "link": "https://example.org/c"}]},
            "https://example.org/c",
        )

    async def _assert_source_url(self, function_name, payload, expected_url):
        with patch.object(
            web_search_module.httpx,
            "AsyncClient",
            return_value=FakeAsyncClient(payload),
        ):
            search = getattr(web_search_module, function_name)
            result = await search("fake-key", "test query", 1)

        self.assertIn(expected_url, result)
        self.assertIn("Example", result)


if __name__ == "__main__":
    unittest.main()
