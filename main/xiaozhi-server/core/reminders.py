import asyncio
import copy
import json
import os
import sqlite3
import time
import uuid
from datetime import date, datetime, timedelta

from config.config_loader import get_private_config_from_api
from config.logger import setup_logging
from core.utils.modules_initialize import initialize_tts

TAG = __name__
logger = setup_logging()

DB_PATH = os.environ.get("REMINDER_DB", "data/reminders.db")
AUDIO_DIR = os.environ.get("REMINDER_AUDIO_DIR", "data/reminder_audio")
AUDIO_BASE_URL = os.environ.get("REMINDER_AUDIO_BASE_URL", "https://aiot.snab.win")
DEFAULT_DEVICE_MAC = os.environ.get("REMINDER_DEVICE_MAC", "").lower()
RETRY_SECONDS = 30
GIVE_UP_SECONDS = 600
AUDIO_KEEP_SECONDS = 86400
PING_SECONDS = 30

active_connections = {}
notify_channels = {}


def register_connection(device_id, conn):
    if device_id:
        active_connections[device_id.lower()] = conn


def unregister_connection(device_id, conn):
    if device_id and active_connections.get(device_id.lower()) is conn:
        active_connections.pop(device_id.lower(), None)


async def serve_notify_channel(websocket, device_id):
    key = (device_id or "").lower()
    if not key:
        await websocket.close()
        return
    previous = notify_channels.get(key)
    notify_channels[key] = websocket
    if previous is not None and previous is not websocket:
        try:
            await previous.close()
        except Exception:
            pass
    logger.bind(tag=TAG).info(f"提醒通道已連線: {key}")

    async def keepalive():
        while True:
            await asyncio.sleep(PING_SECONDS)
            await websocket.ping()

    pinger = asyncio.create_task(keepalive())
    try:
        async for _ in websocket:
            pass
    except Exception:
        pass
    finally:
        pinger.cancel()
        if notify_channels.get(key) is websocket:
            notify_channels.pop(key, None)
        logger.bind(tag=TAG).info(f"提醒通道已中斷: {key}")


def _db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_mac TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            time TEXT NOT NULL,
            date TEXT,
            days TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            next_at REAL,
            retry_at REAL,
            last_fired_at REAL,
            last_status TEXT,
            created_at REAL NOT NULL
        )"""
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
    if "device_mac" not in columns:
        conn.execute("ALTER TABLE reminders ADD COLUMN device_mac TEXT NOT NULL DEFAULT ''")
        if DEFAULT_DEVICE_MAC:
            conn.execute("UPDATE reminders SET device_mac=? WHERE device_mac=''", (DEFAULT_DEVICE_MAC,))
    return conn


def compute_next(time_str, date_str, days, after):
    hour, minute = (int(x) for x in time_str.split(":"))
    if not days:
        if not date_str:
            return None
        target = datetime.combine(date.fromisoformat(date_str), datetime.min.time()).replace(
            hour=hour, minute=minute
        )
        return target.timestamp() if target.timestamp() > after else None
    allowed = {int(d) for d in days.split(",") if d != ""}
    base = datetime.fromtimestamp(after)
    for offset in range(8):
        day = (base + timedelta(days=offset)).date()
        if day.weekday() not in allowed:
            continue
        target = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
        if target.timestamp() > after:
            return target.timestamp()
    return None


def _row(r):
    item = dict(r)
    item["enabled"] = bool(item["enabled"])
    return item


def list_reminders(device_mac):
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE device_mac=? ORDER BY enabled DESC, next_at IS NULL, next_at, id",
            (device_mac.lower(),),
        ).fetchall()
    return [_row(r) for r in rows]


def validate(data):
    device_mac = str(data.get("device_mac") or DEFAULT_DEVICE_MAC).strip().lower()
    text = str(data.get("text", "")).strip()
    time_str = str(data.get("time", "")).strip()
    date_str = str(data.get("date") or "").strip() or None
    days = data.get("days") or []
    if isinstance(days, str):
        days = [d for d in days.split(",") if d != ""]
    days = sorted({int(d) for d in days if 0 <= int(d) <= 6})
    if not device_mac:
        raise ValueError("請選擇提醒裝置")
    if not text or len(text) > 200:
        raise ValueError("提醒內容需為 1 到 200 字")
    datetime.strptime(time_str, "%H:%M")
    if not days:
        if not date_str:
            raise ValueError("單次提醒需要日期")
        date.fromisoformat(date_str)
    else:
        date_str = None
    return device_mac, text, time_str, date_str, ",".join(str(d) for d in days)


def create_reminder(data):
    device_mac, text, time_str, date_str, days = validate(data)
    next_at = compute_next(time_str, date_str, days, time.time())
    if next_at is None:
        raise ValueError("提醒時間已經過去")
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (device_mac, text, time, date, days, enabled, next_at, created_at) VALUES (?,?,?,?,?,1,?,?)",
            (device_mac, text, time_str, date_str, days, next_at, time.time()),
        )
        rid = cur.lastrowid
    return get_reminder(rid)


def update_reminder(rid, data, device_mac):
    current = get_reminder(rid, device_mac)
    if current is None:
        return None
    merged = {**current, **data}
    if isinstance(merged.get("days"), str):
        merged["days"] = [d for d in merged["days"].split(",") if d != ""]
    _, text, time_str, date_str, days = validate({**merged, "device_mac": device_mac})
    enabled = bool(merged.get("enabled", True))
    next_at = compute_next(time_str, date_str, days, time.time()) if enabled else None
    if enabled and next_at is None:
        raise ValueError("提醒時間已經過去")
    with _db() as conn:
        conn.execute(
            "UPDATE reminders SET text=?, time=?, date=?, days=?, enabled=?, next_at=?, retry_at=NULL WHERE id=? AND device_mac=?",
            (text, time_str, date_str, days, int(enabled), next_at, rid, device_mac.lower()),
        )
    return get_reminder(rid, device_mac)


def get_reminder(rid, device_mac=None):
    with _db() as conn:
        if device_mac:
            r = conn.execute("SELECT * FROM reminders WHERE id=? AND device_mac=?", (rid, device_mac.lower())).fetchone()
        else:
            r = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    return _row(r) if r else None


def delete_reminder(rid, device_mac):
    with _db() as conn:
        return conn.execute("DELETE FROM reminders WHERE id=? AND device_mac=?", (rid, device_mac.lower())).rowcount > 0


class ReminderService:
    def __init__(self, config):
        self.config = config
        self.lock = asyncio.Lock()

    async def run(self):
        os.makedirs(AUDIO_DIR, exist_ok=True)
        logger.bind(tag=TAG).info("提醒排程啟動")
        while True:
            try:
                await self.tick()
                self.cleanup_audio()
            except Exception as e:
                logger.bind(tag=TAG).error(f"提醒排程錯誤: {e}")
            await asyncio.sleep(5)

    async def tick(self):
        now = time.time()
        with _db() as conn:
            due = conn.execute(
                "SELECT * FROM reminders WHERE enabled=1 AND next_at IS NOT NULL AND COALESCE(retry_at, next_at) <= ?",
                (now,),
            ).fetchall()
        for r in due:
            await self.fire(_row(r))

    async def fire(self, r):
        now = time.time()
        late = now - r["next_at"]
        if late > GIVE_UP_SECONDS:
            status = "missed"
        else:
            status = await self.deliver(r["device_mac"], r["text"])
        if status in ("offline", "error") and late + RETRY_SECONDS <= GIVE_UP_SECONDS:
            with _db() as conn:
                conn.execute(
                    "UPDATE reminders SET retry_at=?, last_status=? WHERE id=?",
                    (now + RETRY_SECONDS, f"retrying:{status}", r["id"]),
                )
            return
        next_at = compute_next(r["time"], r["date"], r["days"], max(now, r["next_at"]) + 1)
        with _db() as conn:
            conn.execute(
                "UPDATE reminders SET next_at=?, retry_at=NULL, enabled=?, last_fired_at=?, last_status=? WHERE id=?",
                (next_at, int(next_at is not None), now, status, r["id"]),
            )
        logger.bind(tag=TAG).info(f"提醒 #{r['id']} {r['text']} -> {status}")

    async def deliver(self, device_mac, text):
        async with self.lock:
            spoken = f"提醒你，{text}"
            conn = active_connections.get(device_mac.lower())
            if conn is not None and getattr(conn, "tts", None) is not None and not conn.stop_event.is_set():
                from core.handle.intentHandler import speak_txt

                conn.client_abort = False
                conn.sentence_id = uuid.uuid4().hex
                speak_txt(conn, spoken)
                conn.last_activity_time = time.time() * 1000
                return "spoken"
            channel = notify_channels.get(device_mac.lower())
            if channel is None:
                return "offline"
            try:
                name = await self.render_audio(device_mac, spoken)
            except Exception as e:
                logger.bind(tag=TAG).error(f"提醒語音產生失敗: {e}")
                return "error"
            message = {
                "type": "notify",
                "audio_url": f"{AUDIO_BASE_URL}/reminders/audio/{name}",
                "subtitles": [{"start_ms": 0, "text": spoken}],
            }
            try:
                await channel.send(json.dumps(message, ensure_ascii=False))
            except Exception as e:
                logger.bind(tag=TAG).error(f"推送提醒失敗: {e}")
                return "offline"
            return "notified"

    async def tts_instance(self, device_mac):
        cfg = copy.deepcopy(self.config)
        if cfg.get("read_config_from_api"):
            private = await get_private_config_from_api(cfg, device_mac, device_mac)
            if private.get("TTS"):
                cfg["TTS"] = private["TTS"]
                cfg["selected_module"]["TTS"] = private["selected_module"]["TTS"]
        return initialize_tts(cfg)

    async def render_audio(self, device_mac, text):
        tts = await self.tts_instance(device_mac)
        name = f"{uuid.uuid4().hex}.ogg"
        raw = os.path.join(AUDIO_DIR, f"{name}.src")
        out = os.path.join(AUDIO_DIR, name)
        try:
            await tts.text_to_speak(text, raw)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-loglevel", "error", "-i", raw,
                "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k",
                "-application", "voip", "-frame_duration", "60", out,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(err.decode(errors="ignore")[-300:])
        finally:
            if os.path.exists(raw):
                os.remove(raw)
        return name

    def cleanup_audio(self):
        cutoff = time.time() - AUDIO_KEEP_SECONDS
        for name in os.listdir(AUDIO_DIR):
            path = os.path.join(AUDIO_DIR, name)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
