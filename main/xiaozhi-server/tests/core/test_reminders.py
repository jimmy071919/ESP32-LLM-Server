import asyncio
import os
import tempfile
import time
from datetime import datetime

from aiohttp import web
from aiohttp.test_utils import TestServer

os.environ["REMINDER_DB"] = os.path.join(tempfile.mkdtemp(), "r.db")
os.environ["REMINDER_DEVICE_MAC"] = "aa:bb:cc:dd:ee:01"

from core import reminders


def ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp()


def test_once_future_and_past():
    after = ts("2026-11-28 10:00")
    assert reminders.compute_next("10:30", "2026-11-28", "", after) == ts("2026-11-28 10:30")
    assert reminders.compute_next("09:30", "2026-11-28", "", after) is None


def test_daily_rolls_to_tomorrow():
    after = ts("2026-11-28 10:00")
    assert reminders.compute_next("09:00", None, "0,1,2,3,4,5,6", after) == ts("2026-11-29 09:00")


def test_weekdays_skip_weekend():
    after = ts("2026-11-28 10:00")
    assert datetime.fromtimestamp(after).weekday() == 5
    assert reminders.compute_next("08:00", None, "0,1,2,3,4", after) == ts("2026-11-30 08:00")


def test_crud_and_validation():
    future = datetime.fromtimestamp(time.time() + 86400 * 2)
    mac = reminders.DEFAULT_DEVICE_MAC
    item = reminders.create_reminder({"device_mac": mac, "text": "吃藥", "time": "08:00", "date": future.date().isoformat()})
    assert item is not None
    assert item["enabled"] and item["next_at"]
    off = reminders.update_reminder(item["id"], {"enabled": False}, mac)
    assert off is not None
    assert off["next_at"] is None and not off["enabled"]
    daily = reminders.update_reminder(item["id"], {"enabled": True, "days": [0, 1, 2, 3, 4, 5, 6]}, mac)
    assert daily is not None
    assert daily["date"] is None and daily["days"] == "0,1,2,3,4,5,6"
    for bad in ({"device_mac": mac, "text": "", "time": "08:00", "days": [1]}, {"device_mac": mac, "text": "x", "time": "25:00", "days": [1]}, {"device_mac": mac, "text": "x", "time": "08:00"}):
        try:
            reminders.create_reminder(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    assert reminders.delete_reminder(item["id"], mac)
    assert reminders.list_reminders(mac) == []


def test_reminders_are_isolated_by_device():
    first = "aa:bb:cc:dd:ee:01"
    second = "aa:bb:cc:dd:ee:02"
    future = datetime.fromtimestamp(time.time() + 86400 * 2).date().isoformat()
    one = reminders.create_reminder({"device_mac": first, "text": "第一台", "time": "08:00", "date": future})
    two = reminders.create_reminder({"device_mac": second, "text": "第二台", "time": "08:00", "date": future})
    assert one is not None and two is not None
    assert [item["text"] for item in reminders.list_reminders(first)] == ["第一台"]
    assert [item["text"] for item in reminders.list_reminders(second)] == ["第二台"]
    assert reminders.update_reminder(two["id"], {"enabled": False}, first) is None
    assert not reminders.delete_reminder(two["id"], first)
    assert reminders.delete_reminder(one["id"], first)
    assert reminders.delete_reminder(two["id"], second)


def test_device_discovery_and_ownership():
    async def run():
        app = web.Application()

        async def agents(request):
            return web.json_response({"code": 0, "data": [
                {"id": "agent-a", "agentName": "客廳"},
                {"id": "agent-b", "agentName": "書房"}
            ]})

        async def devices(request):
            by_agent = {
                "agent-a": [{"macAddress": "AA:BB:CC:DD:EE:01", "alias": "客廳小智", "board": "atoms3r"}],
                "agent-b": [{"macAddress": "AA:BB:CC:DD:EE:02", "alias": "", "board": "atoms3r"}]
            }
            return web.json_response({"code": 0, "data": by_agent[request.match_info["id"]]})

        app.router.add_get("/manager/agent/list", agents)
        app.router.add_get("/manager/device/bind/{id}", devices)
        server = TestServer(app)
        await server.start_server()
        try:
            from core.api.reminder_handler import ReminderHandler
            handler = ReminderHandler(None, str(server.make_url("/manager")).rstrip("/"))
            found = await handler.user_devices("Bearer test")
            assert len(found) == 2
            assert found[0]["macAddress"] == "aa:bb:cc:dd:ee:01"
            assert found[1]["agentName"] == "書房"
            request = type("Request", (), {"headers": {"Authorization": "Bearer test"}})()
            assert await handler.resolve_device(request, "AA:BB:CC:DD:EE:02") == "aa:bb:cc:dd:ee:02"
            try:
                await handler.resolve_device(request, "AA:BB:CC:DD:EE:99")
                raise AssertionError("unowned device was accepted")
            except PermissionError:
                pass
        finally:
            await server.close()

    asyncio.run(run())


def test_notification_uses_selected_device_channel():
    class Channel:
        def __init__(self):
            self.messages = []

        async def send(self, message):
            self.messages.append(message)

    async def run():
        mac = "aa:bb:cc:dd:ee:02"
        channel = Channel()
        service = reminders.ReminderService({})

        async def render_audio(device_mac, text):
            assert device_mac == mac
            return "audio.ogg"

        service.render_audio = render_audio
        reminders.notify_channels[mac] = channel
        try:
            assert await service.deliver(mac, "書房提醒") == "notified"
            assert '"audio_url": "https://aiot.snab.win/reminders/audio/audio.ogg"' in channel.messages[0]
        finally:
            reminders.notify_channels.pop(mac, None)

    asyncio.run(run())
