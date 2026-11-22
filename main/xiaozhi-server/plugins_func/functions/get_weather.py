"""天氣查詢工具（Open-Meteo）。

- 對外函式名稱維持 ``get_weather``，相容既有 Function Calling 與 Manager API 外掛映射。
- 只使用 Open-Meteo（Geocoding + Forecast）；不存在任何隱藏備援服務。
- 地點優先順序：使用者／LLM 明確提供 → 設定的 default_location → 詢問使用者。
  不會猜測城市，也不會自行以 IP 定位。
- Open-Meteo 免費公用 API 僅限非商業用途；商用請購買方案並設定 ``api_key``，
  程式會改用 customer-*.open-meteo.com 端點。資料授權 CC BY 4.0，回覆需保留來源。

配置（``plugins.get_weather``）::

    provider: openmeteo
    default_location: ""      # 例如 "Taipei"；空字串表示未知時詢問使用者
    country_code: ""          # 可選，ISO 國碼（例如 TW），同名地點時優先此國家
    api_key: ""               # Open-Meteo 商用 API key，可留空
    timeout: 8
    forecast_days: 7
    # 進階：自架 Open-Meteo 時可覆寫
    # geocoding_url: https://geocoding-api.open-meteo.com/v1/search
    # forecast_url: https://api.open-meteo.com/v1/forecast

舊版和風天氣（QWeather）設定（有 ``api_host``）中的 ``api_key`` 會被忽略，不再對其發出請求。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

from config.logger import setup_logging
from plugins_func.register import Action, ActionResponse, ToolType, register_function

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

PROVIDER_OPENMETEO = "openmeteo"
SUPPORTED_PROVIDERS = (PROVIDER_OPENMETEO,)

PUBLIC_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
PUBLIC_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CUSTOMER_GEOCODING_URL = "https://customer-geocoding-api.open-meteo.com/v1/search"
CUSTOMER_FORECAST_URL = "https://customer-api.open-meteo.com/v1/forecast"

ATTRIBUTION = "資料來源：Open-Meteo.com（CC BY 4.0）"

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "查詢指定地點目前天氣與未來數日預報。"
            "若上下文已提供該地點的天氣資料，直接使用，不必再呼叫。"
            "使用者沒有說地點、上下文也沒有裝置位置時，可不帶 location 呼叫；"
            "若工具回覆無法確定地點，請詢問使用者想查哪個城市，不要自行猜測。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "城市或地名。建議使用英文或羅馬拼音名稱以提高辨識率，"
                        "例如 Taipei、Kaohsiung、Tokyo、New York。可選。"
                    ),
                },
                "lang": {
                    "type": "string",
                    "description": "使用者的語言代碼，例如 zh_TW、en_US、ja_JP，預設 zh_TW",
                },
            },
            "required": [],
        },
    },
}

# WMO Weather interpretation codes（Open-Meteo 文件）
WMO_CODE_MAP: Dict[int, str] = {
    0: "晴朗",
    1: "大致晴朗",
    2: "局部多雲",
    3: "陰天",
    45: "有霧",
    48: "霧淞",
    51: "微弱毛毛雨",
    53: "毛毛雨",
    55: "較強毛毛雨",
    56: "微弱凍毛毛雨",
    57: "凍毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "微弱凍雨",
    67: "凍雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "霰",
    80: "短暫陣雨",
    81: "陣雨",
    82: "強陣雨",
    85: "陣雪",
    86: "強陣雪",
    95: "雷雨",
    96: "雷雨伴隨小冰雹",
    99: "雷雨伴隨冰雹",
}

_ADMIN_SUFFIX = re.compile(r"(特別行政區|自治區|直轄市|市|縣|县|區|区|鄉|乡|鎮|镇|省)$")
_CJK = re.compile(r"[\u3400-\u9fff]")


class WeatherError(Exception):
    """可直接回覆給 LLM 的錯誤（訊息不含金鑰）。"""


def describe_weather_code(code: Any) -> str:
    try:
        return WMO_CODE_MAP.get(int(code), "未知天氣")
    except (TypeError, ValueError):
        return "未知天氣"


def _lang_to_geocoding_language(lang: Optional[str]) -> str:
    value = (lang or "").lower().replace("-", "_")
    if not value or value.startswith("en"):
        return "en"
    if value.startswith("zh"):
        return "zh"
    return value.split("_")[0]


def get_weather_config(config: Dict[str, Any]) -> Dict[str, Any]:
    weather = ((config or {}).get("plugins") or {}).get("get_weather") or {}
    return weather if isinstance(weather, dict) else {}


def resolve_provider(weather_config: Dict[str, Any]) -> str:
    provider = str(weather_config.get("provider") or PROVIDER_OPENMETEO).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise WeatherError(f"天氣服務 provider「{provider}」不受支援，目前僅支援 openmeteo。")
    return provider


def _endpoints(weather_config: Dict[str, Any]) -> Tuple[str, str, Dict[str, str]]:
    # 有 api_host 代表是舊版和風天氣設定，其 api_key 不能送給 Open-Meteo
    api_key = "" if weather_config.get("api_host") else str(weather_config.get("api_key") or "").strip()
    if api_key:
        geocoding = weather_config.get("geocoding_url") or CUSTOMER_GEOCODING_URL
        forecast = weather_config.get("forecast_url") or CUSTOMER_FORECAST_URL
        return geocoding, forecast, {"apikey": api_key}
    geocoding = weather_config.get("geocoding_url") or PUBLIC_GEOCODING_URL
    forecast = weather_config.get("forecast_url") or PUBLIC_FORECAST_URL
    return geocoding, forecast, {}


def _timeout(weather_config: Dict[str, Any]) -> httpx.Timeout:
    try:
        total = float(weather_config.get("timeout") or 8)
    except (TypeError, ValueError):
        total = 8.0
    return httpx.Timeout(total)


def location_candidates(location: str) -> List[str]:
    """產生地名變體。地名資料庫常只收錄「台北市」而非「台北」，或只收錄「台」而非「臺」。"""
    location = location.strip()
    candidates = [location]
    stripped = _ADMIN_SUFFIX.sub("", location)
    if stripped and stripped != location:
        candidates.append(stripped)
    elif _CJK.search(location) and len(location) <= 4:
        candidates.append(location + "市")
    for value in list(candidates):
        if "臺" in value:
            candidates.append(value.replace("臺", "台"))
    return list(dict.fromkeys(c for c in candidates if c))


async def geocode_location(
    client: httpx.AsyncClient,
    location: str,
    lang: str,
    weather_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """查詢所有地名變體，選擇人口最多的結果，避免同名小鎮（例如「高雄」誤判為四川高雄鎮）。

    可用 ``country_code``（ISO-3166-1 alpha-2，例如 TW）優先限定國家；限定後查無結果才放寬。
    """
    geocoding_url, _, auth = _endpoints(weather_config)
    language = _lang_to_geocoding_language(lang)
    country = str(weather_config.get("country_code") or "").strip().upper()
    candidates = location_candidates(location)

    async def search(country_code: str) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        for candidate in candidates:
            params = {"name": candidate, "count": 10, "language": language, "format": "json", **auth}
            if country_code:
                params["countryCode"] = country_code
            response = await client.get(geocoding_url, params=params)
            if response.status_code != 200:
                raise WeatherError(f"地點查詢服務暫時無法使用（HTTP {response.status_code}）。")
            found.extend((response.json() or {}).get("results") or [])
        return found

    results = await search(country) if country else []
    if not results:
        results = await search("")
    if not results:
        return None
    return max(results, key=lambda r: r.get("population") or 0)


async def fetch_forecast(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    weather_config: Dict[str, Any],
) -> Dict[str, Any]:
    _, forecast_url, auth = _endpoints(weather_config)
    try:
        days = max(1, min(16, int(weather_config.get("forecast_days") or 7)))
    except (TypeError, ValueError):
        days = 7
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
        "precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": days,
        **auth,
    }
    response = await client.get(forecast_url, params=params)
    if response.status_code != 200:
        raise WeatherError(f"天氣預報服務暫時無法使用（HTTP {response.status_code}）。")
    return response.json() or {}


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        value = round(value, 1)
        if value == int(value):
            value = int(value)
    return f"{value}{unit}"


def format_weather_report(place: Dict[str, Any], forecast: Dict[str, Any]) -> str:
    place_name = "，".join(
        dict.fromkeys(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p)
    )
    current = forecast.get("current") or {}
    units = forecast.get("current_units") or {}
    temp_unit = units.get("temperature_2m", "°C")
    wind_unit = units.get("wind_speed_10m", "km/h")

    lines = [f"查詢地點：{place_name}"]
    if forecast.get("timezone"):
        lines.append(f"當地時區：{forecast['timezone']}")
    if current:
        lines.append(
            "目前天氣："
            f"{describe_weather_code(current.get('weather_code'))}，"
            f"氣溫 {_fmt(current.get('temperature_2m'), temp_unit)}"
            f"（體感 {_fmt(current.get('apparent_temperature'), temp_unit)}），"
            f"濕度 {_fmt(current.get('relative_humidity_2m'), '%')}，"
            f"風速 {_fmt(current.get('wind_speed_10m'), wind_unit)}，"
            f"降水 {_fmt(current.get('precipitation'), 'mm')}"
        )
        if current.get("time"):
            lines.append(f"觀測時間：{current['time']}")

    daily = forecast.get("daily") or {}
    dates = daily.get("time") or []
    if dates:
        codes = daily.get("weather_code") or []
        highs = daily.get("temperature_2m_max") or []
        lows = daily.get("temperature_2m_min") or []
        rain = daily.get("precipitation_probability_max") or []

        def at(values, i):
            return values[i] if i < len(values) else None

        lines.append("")
        lines.append(f"未來 {len(dates)} 天預報：")
        for i, date in enumerate(dates):
            line = (
                f"{date}：{describe_weather_code(at(codes, i))}，"
                f"氣溫 {_fmt(at(lows, i), temp_unit)}～{_fmt(at(highs, i), temp_unit)}"
            )
            if at(rain, i) is not None:
                line += f"，降雨機率 {_fmt(at(rain, i), '%')}"
            lines.append(line)

    lines.append("")
    lines.append(ATTRIBUTION)
    lines.append("（回答時以口語摘要重點，不要逐字唸出所有數字或來源網址）")
    return "\n".join(lines)


async def fetch_weather_report(
    config: Dict[str, Any],
    location: Optional[str],
    lang: Optional[str] = "zh_TW",
) -> Tuple[bool, str]:
    """回傳 (成功與否, 報告或錯誤訊息)。供工具與系統提示詞上下文共用；失敗結果不快取。"""
    from core.utils.cache.manager import CacheType, cache_manager

    weather_config = get_weather_config(config)
    try:
        provider = resolve_provider(weather_config)
    except WeatherError as e:
        return False, str(e)

    location = (location or "").strip() or str(weather_config.get("default_location") or "").strip()
    if not location:
        return False, "無法確定要查詢天氣的地點，請詢問使用者想查哪個城市。"

    lang = lang or "zh_TW"
    cache_key = f"{provider}:{location.lower()}:{_lang_to_geocoding_language(lang)}"
    cached = cache_manager.get(CacheType.WEATHER, cache_key)
    if cached:
        return True, cached

    try:
        async with httpx.AsyncClient(timeout=_timeout(weather_config)) as client:
            place = await geocode_location(client, location, lang, weather_config)
            if not place:
                return False, f"找不到地點「{location}」，請使用者確認城市名稱（可改用英文名稱）。"
            forecast = await fetch_forecast(client, place["latitude"], place["longitude"], weather_config)
    except WeatherError as e:
        logger.bind(tag=TAG).warning(f"天氣查詢失敗：{e}")
        return False, str(e)
    except httpx.TimeoutException:
        logger.bind(tag=TAG).warning("天氣查詢逾時")
        return False, "天氣服務回應逾時，請稍後再試。"
    except Exception as e:  # noqa: BLE001
        logger.bind(tag=TAG).error(f"天氣查詢異常：{e}")
        return False, "天氣服務暫時無法使用，請稍後再試。"

    report = format_weather_report(place, forecast)
    cache_manager.set(CacheType.WEATHER, cache_key, report)
    return True, report


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
async def get_weather(conn: "ConnectionHandler", location: str = None, lang: str = "zh_TW"):
    ok, text = await fetch_weather_report(conn.config, location, lang)
    if not ok:
        logger.bind(tag=TAG).info(f"get_weather 未取得資料：{text}")
    return ActionResponse(Action.REQLLM, text, None)
