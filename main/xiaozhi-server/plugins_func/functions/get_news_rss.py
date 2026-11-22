"""RSS／Atom 新聞閘道（取代 newsnow 聚合與中新網預設）。

- 新聞來源白名單完全由設定管理，程式內沒有任何預設或隱藏備援來源。
- 只取標題、發布時間、連結與 RSS 提供的摘要；不抓取、不重製全文。
- 支援 RSS 2.0、RSS 1.0（RDF）與 Atom；只允許 https 來源。

配置（``plugins.get_news_rss``）::

    # 每行（或以分號分隔）一個來源：名稱|https 網址|語言(可選)|主題(可選，逗號分隔)
    feeds: |
      BBC 中文|https://feeds.bbci.co.uk/zhongwen/trad/rss.xml|zh|world
      BBC World|https://feeds.bbci.co.uk/news/world/rss.xml|en|world
    max_items: 5          # 一次最多回傳幾則
    max_age_hours: 72     # 只保留多久以內的新聞（無日期的條目保留）
    timeout: 8            # 單一來源逾時秒數
    cache_seconds: 600    # 來源快取秒數

也可在 YAML 用清單：``feeds: [{name: ..., url: ..., language: zh, topics: [world]}]``。
使用前請逐一確認各來源 RSS 的使用條款；本工具僅提供標題、摘要與原文連結。
"""

from __future__ import annotations

import asyncio
import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from config.logger import setup_logging
from plugins_func.register import Action, ActionResponse, ToolType, register_function

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

MAX_FEED_BYTES = 2 * 1024 * 1024
SUMMARY_CHARS = 180
DETAIL_CHARS = 800

GET_NEWS_RSS_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news_rss",
        "description": (
            "使用者想看或聽新聞時呼叫（例如「來點新聞」「今天國際有什麼大事」）。"
            "可指定來源、主題關鍵字或語言。"
            "使用者說「詳細說說」「這則講什麼」時，用 detail=true 取得上一次列出新聞的摘要。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "新聞來源名稱（須為已設定的來源），可選",
                },
                "topic": {
                    "type": "string",
                    "description": "主題或關鍵字，例如 world、科技、經濟、AI，可選",
                },
                "language": {
                    "type": "string",
                    "description": "偏好的新聞語言，例如 zh、en、ja，可選",
                },
                "detail": {
                    "type": "boolean",
                    "description": "是否取得上一次列出新聞的詳細摘要，預設 false",
                },
                "index": {
                    "type": "integer",
                    "description": "detail=true 時要看第幾則（從 1 開始），預設 1",
                },
            },
            "required": [],
        },
    },
}

_feed_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------- 設定解析


def parse_feeds(raw: Any) -> List[Dict[str, Any]]:
    """把設定轉成 [{name, url, language, topics}]；非 https 或格式錯誤的條目直接丟棄。"""
    entries: List[Dict[str, Any]] = []
    if not raw:
        return entries
    if isinstance(raw, str):
        items: List[Any] = [p for p in re.split(r"[;\n]", raw) if p.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        return entries

    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            language = str(item.get("language") or item.get("lang") or "").strip().lower()
            topics = item.get("topics") or []
            if isinstance(topics, str):
                topics = [t for t in re.split(r"[,，]", topics)]
        else:
            parts = [p.strip() for p in str(item).split("|")]
            if len(parts) < 2:
                continue
            name, url = parts[0], parts[1]
            language = parts[2].lower() if len(parts) > 2 else ""
            topics = re.split(r"[,，]", parts[3]) if len(parts) > 3 else []
        parsed = urlparse(url)
        if not name or parsed.scheme != "https" or not parsed.netloc:
            logger.bind(tag=TAG).warning(f"忽略無效的新聞來源設定：{name or url}")
            continue
        entries.append(
            {
                "name": name,
                "url": url,
                "language": language,
                "topics": [t.strip().lower() for t in topics if t and t.strip()],
            }
        )
    return entries


def _news_config(config: Dict[str, Any]) -> Dict[str, Any]:
    value = ((config or {}).get("plugins") or {}).get("get_news_rss") or {}
    return value if isinstance(value, dict) else {}


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- RSS 解析


def clean_text(value: Optional[str], limit: int = SUMMARY_CHARS) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _text(element: Optional[ET.Element], *paths: str) -> str:
    if element is None:
        return ""
    for path in paths:
        found = element.find(path)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def parse_feed_xml(content: bytes, source_name: str) -> List[Dict[str, Any]]:
    """解析 RSS 2.0／RSS 1.0（RDF）／Atom。拒絕含 DOCTYPE／ENTITY 的文件以避免 XML 炸彈。"""
    head = content[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in content.lower():
        raise ValueError("feed contains DOCTYPE/ENTITY declarations")
    root = ET.fromstring(content)
    items: List[Dict[str, Any]] = []

    rss_items = root.findall(".//item") or root.findall(f".//{_RSS1}item")
    for node in rss_items:
        title = _text(node, "title", f"{_RSS1}title")
        link = _text(node, "link", f"{_RSS1}link", "guid")
        summary = _text(node, "description", f"{_RSS1}description")
        published = _text(node, "pubDate", f"{_DC}date")
        if title:
            items.append(_item(source_name, title, link, summary, published))

    for node in root.findall(f".//{_ATOM}entry"):
        title = _text(node, f"{_ATOM}title")
        link = ""
        for link_node in node.findall(f"{_ATOM}link"):
            if link_node.get("rel", "alternate") == "alternate" and link_node.get("href"):
                link = link_node.get("href")
                break
        summary = _text(node, f"{_ATOM}summary", f"{_ATOM}content")
        published = _text(node, f"{_ATOM}published", f"{_ATOM}updated")
        if title:
            items.append(_item(source_name, title, link, summary, published))
    return items


def _item(source: str, title: str, link: str, summary: str, published: str) -> Dict[str, Any]:
    return {
        "source": source,
        "title": clean_text(title, 200),
        "link": link if link.startswith(("https://", "http://")) else "",
        "summary": clean_text(summary, DETAIL_CHARS),
        "published": parse_date(published),
    }


# ---------------------------------------------------------------- 抓取


async def fetch_feed(
    client: httpx.AsyncClient, feed: Dict[str, Any], cache_seconds: int
) -> List[Dict[str, Any]]:
    now = time.monotonic()
    cached = _feed_cache.get(feed["url"])
    if cached and now - cached[0] < cache_seconds:
        return cached[1]
    response = await client.get(feed["url"], headers={"User-Agent": "xiaozhi-news-rss/1.0"})
    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}")
    content = response.content
    if len(content) > MAX_FEED_BYTES:
        raise ValueError("feed too large")
    items = parse_feed_xml(content, feed["name"])
    _feed_cache[feed["url"]] = (now, items)
    return items


def select_feeds(
    feeds: List[Dict[str, Any]], source: Optional[str], language: Optional[str], topic: Optional[str]
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if source:
        wanted = source.strip().lower()
        matched = [f for f in feeds if wanted in f["name"].lower() or f["name"].lower() in wanted]
        if not matched:
            names = "、".join(f["name"] for f in feeds)
            return [], f"沒有設定名為「{source}」的新聞來源。可用來源：{names}。"
        return matched, None
    selected = feeds
    if language:
        lang = language.strip().lower().replace("-", "_").split("_")[0]
        by_lang = [f for f in selected if not f["language"] or f["language"].startswith(lang)]
        selected = by_lang or selected
    if topic:
        wanted = topic.strip().lower()
        by_topic = [f for f in selected if wanted in f["topics"]]
        selected = by_topic or selected
    return selected, None


def merge_items(
    groups: List[List[Dict[str, Any]]], topic: Optional[str], max_age_hours: int, limit: int
) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    seen = set()
    merged: List[Dict[str, Any]] = []
    for group in groups:
        for item in group:
            if item["published"] and item["published"] < cutoff:
                continue
            key = item["link"] or item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    if topic:
        wanted = topic.strip().lower()
        filtered = [i for i in merged if wanted in i["title"].lower() or wanted in i["summary"].lower()]
        merged = filtered or merged
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    merged.sort(key=lambda i: i["published"] or epoch, reverse=True)
    return merged[:limit]


def _fmt_time(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "時間未提供"


def format_headlines(items: List[Dict[str, Any]], failed: List[str]) -> str:
    lines = ["【新聞標題】"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['title']}（{item['source']}，{_fmt_time(item['published'])}）")
        if item["summary"]:
            lines.append(f"   摘要：{clean_text(item['summary'])}")
        if item["link"]:
            lines.append(f"   來源網址：{item['link']}")
    if failed:
        lines.append(f"（以下來源暫時無法取得：{'、'.join(failed)}）")
    lines.append(
        "請用使用者的語言口語化地挑重點播報，說出來源名稱，不要唸出網址；"
        "可詢問使用者想聽哪一則的細節。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------- 工具入口


@register_function("get_news_rss", GET_NEWS_RSS_FUNCTION_DESC, ToolType.SYSTEM_CTL)
async def get_news_rss(
    conn: "ConnectionHandler",
    source: str = None,
    topic: str = None,
    language: str = None,
    detail: bool = False,
    index: int = 1,
):
    news_config = _news_config(conn.config)

    if detail:
        last = getattr(conn, "last_news_rss_items", None) or []
        if not last:
            return ActionResponse(Action.REQLLM, "目前沒有可查看細節的新聞，請先列出新聞。", None)
        position = _int(index, 1, 1, len(last)) - 1
        item = last[position]
        text = (
            f"新聞標題：{item['title']}\n來源：{item['source']}，{_fmt_time(item['published'])}\n"
            f"RSS 摘要：{item['summary'] or '來源未提供摘要'}\n"
        )
        if item["link"]:
            text += f"來源網址：{item['link']}\n"
        text += "（只根據上述摘要口語說明，不要杜撰摘要沒有的細節；若需全文請使用者開啟原文連結）"
        return ActionResponse(Action.REQLLM, text, None)

    feeds = parse_feeds(news_config.get("feeds"))
    if not feeds:
        return ActionResponse(Action.REQLLM, "新聞來源尚未設定，請管理員在外掛設定中加入 RSS 來源。", None)

    selected, error = select_feeds(feeds, source, language, topic)
    if error:
        return ActionResponse(Action.REQLLM, error, None)

    limit = _int(news_config.get("max_items"), 5, 1, 20)
    max_age = _int(news_config.get("max_age_hours"), 72, 1, 24 * 30)
    cache_seconds = _int(news_config.get("cache_seconds"), 600, 0, 24 * 3600)
    timeout = float(_int(news_config.get("timeout"), 8, 1, 60))

    # 連線逾時與總逾時相同：部分來源首次連線（DNS／TLS）較慢，過短的 connect 逾時會造成誤判
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        results = await asyncio.gather(
            *(fetch_feed(client, feed, cache_seconds) for feed in selected),
            return_exceptions=True,
        )

    groups: List[List[Dict[str, Any]]] = []
    failed: List[str] = []
    for feed, result in zip(selected, results):
        if isinstance(result, Exception):
            logger.bind(tag=TAG).warning(f"新聞來源 {feed['name']} 取得失敗：{result}")
            failed.append(feed["name"])
        else:
            groups.append(result)

    items = merge_items(groups, topic, max_age, limit)
    if not items:
        message = "目前沒有取得符合條件的新聞。"
        if failed:
            message += f"無法連線的來源：{'、'.join(failed)}。"
        return ActionResponse(Action.REQLLM, message, None)

    conn.last_news_rss_items = items
    return ActionResponse(Action.REQLLM, format_headlines(items, failed), None)
