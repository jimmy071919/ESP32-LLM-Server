"""Open-Meteo weather tool: no hidden providers, no guessed city, correct endpoints."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugins_func.functions import get_weather as weather
from plugins_func.register import Action

GEOCODE = {"results": [{"name": "Taipei", "admin1": "Taipei", "country": "Taiwan", "latitude": 25.05, "longitude": 121.53}]}
FORECAST = {
    "timezone": "Asia/Taipei",
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": {
        "time": "2026-11-22T21:00",
        "temperature_2m": 21.4,
        "apparent_temperature": 22.0,
        "relative_humidity_2m": 80,
        "precipitation": 0.0,
        "weather_code": 3,
        "wind_speed_10m": 9.5,
    },
    "daily": {
        "time": ["2026-11-22", "2026-11-23"],
        "weather_code": [3, 61],
        "temperature_2m_max": [24.0, 22.5],
        "temperature_2m_min": [18.0, 17.0],
        "precipitation_probability_max": [10, 70],
    },
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class RecordingClient:
    """Fake httpx.AsyncClient that answers geocoding / forecast and records requests."""

    def __init__(self, geocode=GEOCODE, forecast=FORECAST, status=200):
        self.calls = []
        self.geocode = geocode
        self.forecast = forecast
        self.status = status

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, params=None, **kwargs):
        self.calls.append((url, dict(params or {})))
        if self.status != 200:
            return FakeResponse({}, self.status)
        if "geocoding" in url:
            return FakeResponse(self.geocode)
        return FakeResponse(self.forecast)


def conn(settings=None):
    return SimpleNamespace(config={"plugins": {"get_weather": settings or {}}}, client_ip="203.0.113.7")


class WeatherToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from core.utils.cache.manager import CacheType, cache_manager

        cache_manager.clear(CacheType.WEATHER) if hasattr(cache_manager, "clear") else None

    async def test_unknown_location_asks_user_without_network(self):
        client = RecordingClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            result = await weather.get_weather(conn({"default_location": ""}))
        self.assertEqual(result.action, Action.REQLLM)
        self.assertIn("詢問使用者", result.result)
        self.assertEqual(client.calls, [])

    async def test_unsupported_provider_fails_closed(self):
        client = RecordingClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            result = await weather.get_weather(conn({"provider": "qweather"}), location="Taipei")
        self.assertIn("不受支援", result.result)
        self.assertEqual(client.calls, [])

    async def test_public_endpoints_and_report(self):
        client = RecordingClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            result = await weather.get_weather(conn({"provider": "openmeteo"}), location="Taipei-public", lang="zh_TW")
        urls = [c[0] for c in client.calls]
        self.assertEqual(urls, [weather.PUBLIC_GEOCODING_URL, weather.PUBLIC_FORECAST_URL])
        self.assertTrue(all("open-meteo.com" in u for u in urls))
        self.assertNotIn("apikey", client.calls[1][1])
        self.assertEqual(client.calls[0][1]["language"], "zh")
        self.assertIn("Taipei", result.result)
        self.assertIn("陰天", result.result)
        self.assertIn("小雨", result.result)
        self.assertIn("降雨機率 70%", result.result)
        self.assertIn("Open-Meteo", result.result)

    async def test_default_location_used_when_none_given(self):
        client = RecordingClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            await weather.get_weather(conn({"default_location": "Kaohsiung-default"}))
        self.assertEqual(client.calls[0][1]["name"], "Kaohsiung-default")

    async def test_commercial_key_uses_customer_endpoints(self):
        client = RecordingClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            await weather.get_weather(conn({"provider": "openmeteo", "api_key": "om-key"}), location="Taipei-paid")
        self.assertEqual(client.calls[0][0], weather.CUSTOMER_GEOCODING_URL)
        self.assertEqual(client.calls[1][1]["apikey"], "om-key")

    async def test_legacy_qweather_key_is_never_sent(self):
        client = RecordingClient()
        legacy = {"api_host": "xxxx.re.qweatherapi.com", "api_key": "legacy-key", "default_location": "Taipei-legacy"}
        with patch.object(weather.httpx, "AsyncClient", client):
            result = await weather.get_weather(conn(legacy))
        self.assertTrue(all("qweather" not in c[0] for c in client.calls))
        self.assertTrue(all("legacy-key" not in str(c[1]) for c in client.calls))
        self.assertIn("Taipei", result.result)

    async def test_admin_suffix_retry(self):
        self.assertEqual(weather.location_candidates("臺北市"), ["臺北市", "臺北", "台北市", "台北"])
        self.assertEqual(weather.location_candidates("台北"), ["台北", "台北市"])
        self.assertEqual(weather.location_candidates("Taipei"), ["Taipei"])

    async def test_picks_most_populous_match_across_candidates_and_country_bias(self):
        town = {"name": "高雄", "admin1": "四川", "country": "中国", "latitude": 30.0, "longitude": 104.0, "population": 0}
        city = {"name": "高雄市", "admin1": "高雄", "country": "台湾", "latitude": 22.6, "longitude": 120.3, "population": 2700000}

        class MultiClient(RecordingClient):
            async def get(self, url, params=None, **kwargs):
                self.calls.append((url, dict(params or {})))
                if "geocoding" in url:
                    if params.get("countryCode") == "TW":
                        return FakeResponse({"results": [city]} if params["name"] == "高雄市" else {})
                    return FakeResponse({"results": [town] if params["name"] == "高雄" else [city]})
                return FakeResponse(FORECAST)

        client = MultiClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            ok, text = await weather.fetch_weather_report(conn().config, "高雄", "zh_TW")
        self.assertTrue(ok)
        self.assertIn("高雄市", text)
        self.assertEqual(client.calls[-1][1]["latitude"], 22.6)

        client = MultiClient()
        with patch.object(weather.httpx, "AsyncClient", client):
            ok, text = await weather.fetch_weather_report(conn({"country_code": "tw"}).config, "高雄", "en_US")
        self.assertEqual([c[1].get("countryCode") for c in client.calls if "geocoding" in c[0]], ["TW", "TW"])

    async def test_not_found_and_http_error_are_not_cached(self):
        ok, text = False, ""
        with patch.object(weather.httpx, "AsyncClient", RecordingClient(geocode={"results": []})):
            ok, text = await weather.fetch_weather_report(conn().config, "Nowhere-x")
        self.assertFalse(ok)
        self.assertIn("找不到", text)
        with patch.object(weather.httpx, "AsyncClient", RecordingClient(status=503)):
            ok, text = await weather.fetch_weather_report(conn().config, "Nowhere-x")
        self.assertFalse(ok)
        self.assertIn("503", text)
        with patch.object(weather.httpx, "AsyncClient", RecordingClient()):
            ok, _ = await weather.fetch_weather_report(conn().config, "Nowhere-x")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
