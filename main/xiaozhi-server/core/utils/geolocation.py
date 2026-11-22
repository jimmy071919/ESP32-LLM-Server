"""IP 粗略定位（可選、預設關閉）。

設計原則：
- 預設 ``provider: none``，不把使用者 IP 送到任何第三方服務。
- 只允許明確列出的非中國供應商；未知 provider 直接視為關閉，不會悄悄回退。
- 私有網段 IP 預設不查詢（避免把伺服器自己的公網 IP 當成裝置位置）；
  家用單機部署可設定 ``lookup_private_ip_as_server: true``，以伺服器出口 IP 估計位置。

配置（``config.yaml`` 頂層，或 Manager API ``sys_params`` 的 ``geolocation.*``）::

    geolocation:
      provider: none        # none / ipinfo / ipwhois
      api_key: ""           # ipinfo 需要 token；ipwhois 免費版不需要
      timeout: 3
      lookup_private_ip_as_server: false
"""

from __future__ import annotations

import ipaddress
from typing import Any, Callable, Dict, Optional

import requests

TAG = __name__

SUPPORTED_PROVIDERS = ("ipinfo", "ipwhois")
DISABLED_PROVIDERS = ("", "none", "off", "disabled", "false")


def is_private_or_local_ip(ip_addr: Optional[str]) -> bool:
    if not ip_addr:
        return True
    try:
        ip = ipaddress.ip_address(ip_addr.strip())
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def get_geolocation_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    geo = config.get("geolocation") or {}
    return geo if isinstance(geo, dict) else {}


def _parse_ipinfo(data: Dict[str, Any]) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "city": data.get("city") or "",
        "region": data.get("region") or "",
        "country": data.get("country") or "",
    }
    loc = data.get("loc") or ""
    if "," in loc:
        lat, lon = loc.split(",", 1)
        try:
            info["latitude"] = float(lat)
            info["longitude"] = float(lon)
        except ValueError:
            pass
    if data.get("timezone"):
        info["timezone"] = data["timezone"]
    return info


def _parse_ipwhois(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("success") is False:
        return {}
    info: Dict[str, Any] = {
        "city": data.get("city") or "",
        "region": data.get("region") or "",
        "country": data.get("country_code") or data.get("country") or "",
    }
    for key in ("latitude", "longitude"):
        if isinstance(data.get(key), (int, float)):
            info[key] = float(data[key])
    timezone = data.get("timezone")
    if isinstance(timezone, dict) and timezone.get("id"):
        info["timezone"] = timezone["id"]
    return info


def _build_request(provider: str, ip_addr: str, api_key: str):
    if provider == "ipinfo":
        path = f"{ip_addr}/json" if ip_addr else "json"
        params = {"token": api_key} if api_key else None
        return f"https://ipinfo.io/{path}", params, _parse_ipinfo
    if provider == "ipwhois":
        return f"https://ipwho.is/{ip_addr}", None, _parse_ipwhois
    return None, None, None


def lookup_ip_location(
    ip_addr: Optional[str],
    config: Optional[Dict[str, Any]] = None,
    logger=None,
    http_get: Callable[..., Any] = requests.get,
) -> Dict[str, Any]:
    """回傳 ``{"city": ..., "region": ..., "country": ..., ...}``；未啟用或失敗時回傳 ``{}``。"""
    geo = get_geolocation_config(config)
    provider = str(geo.get("provider") or "none").strip().lower()
    if provider in DISABLED_PROVIDERS:
        return {}
    if provider not in SUPPORTED_PROVIDERS:
        if logger:
            logger.bind(tag=TAG).warning(
                f"geolocation.provider={provider} 不在允許清單 {SUPPORTED_PROVIDERS}，已停用 IP 定位"
            )
        return {}

    target_ip = (ip_addr or "").strip()
    if is_private_or_local_ip(target_ip):
        if not geo.get("lookup_private_ip_as_server"):
            return {}
        target_ip = ""  # 由供應商以請求來源 IP（即伺服器出口）定位

    api_key = str(geo.get("api_key") or "").strip()
    url, params, parser = _build_request(provider, target_ip, api_key)
    try:
        timeout = float(geo.get("timeout") or 3)
    except (TypeError, ValueError):
        timeout = 3.0
    try:
        resp = http_get(url, params=params, timeout=timeout)
        if getattr(resp, "status_code", 200) != 200:
            if logger:
                logger.bind(tag=TAG).warning(
                    f"IP 定位失敗：provider={provider} status={resp.status_code}"
                )
            return {}
        return parser(resp.json() or {})
    except Exception as e:  # noqa: BLE001 - 定位失敗不可影響對話
        if logger:
            logger.bind(tag=TAG).warning(f"IP 定位失敗：provider={provider} error={e}")
        return {}
