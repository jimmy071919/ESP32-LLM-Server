"""Workbench text can be answered (and spoken) by the physical device connection."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.handle.textHandler import listenMessageHandler as listen
from core.handle import sendAudioHandle
from core.utils.connection_registry import ConnectionRegistry


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(payload)


class FakeHandler(SimpleNamespace):
    """Hashable by identity, like the real ConnectionHandler."""

    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other


def handler(device_id, web=False, ready=True, first=0):
    return FakeHandler(
        device_id=device_id,
        web_chat_mode=web,
        websocket=FakeSocket(),
        tts=object() if ready else None,
        llm=object() if ready else None,
        first_activity_time=first,
        mirror_connections=set(),
        session_id=f"s-{device_id}-{web}-{first}",
        logger=MagicMock(),
        last_activity_time=0,
        just_woken_up=False,
    )


class FakeServer:
    """Mirrors the WebSocketServer delegation methods."""

    def __init__(self):
        self.connection_registry = ConnectionRegistry()
        self.register_connection = self.connection_registry.register
        self.unregister_connection = self.connection_registry.unregister
        self.find_device_connection = self.connection_registry.find_device_connection


def server():
    return FakeServer()


class RegistryTests(unittest.TestCase):
    def test_find_prefers_ready_newest_physical_connection(self):
        srv = server()
        web = handler("AA", web=True, first=9)
        old = handler("AA", first=1)
        new_not_ready = handler("AA", ready=False, first=5)
        newest = handler("AA", first=3)
        other = handler("BB", first=7)
        for h in (web, old, new_not_ready, newest, other):
            srv.register_connection(h)
        self.assertIs(srv.find_device_connection("AA", exclude=web), newest)
        self.assertIsNone(srv.find_device_connection("CC"))

    def test_unregister_removes_mirrors(self):
        srv = server()
        web, device = handler("AA", web=True), handler("AA")
        srv.register_connection(web)
        srv.register_connection(device)
        device.mirror_connections.add(web)
        srv.unregister_connection(web)
        self.assertNotIn(web, device.mirror_connections)
        srv.unregister_connection(device)
        self.assertEqual(srv.connection_registry.device_connections, {})


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_to_device_and_mirrors(self):
        srv = server()
        web, device = handler("AA", web=True), handler("AA")
        web.server = srv
        srv.register_connection(web)
        srv.register_connection(device)
        with patch.object(listen, "startToChat", new_callable=AsyncMock) as chat, \
                patch.object(listen, "enqueue_asr_report") as report:
            routed = await listen.route_text_to_device(web, "今天天氣")
        self.assertTrue(routed)
        chat.assert_awaited_once_with(device, "今天天氣")
        report.assert_called_once_with(device, "今天天氣", [])
        self.assertIn(web, device.mirror_connections)
        self.assertEqual(json.loads(web.websocket.sent[-1])["state"], "device_routed")

        await sendAudioHandle._send_to_mirrors(device, '{"type": "tts"}')
        self.assertEqual(web.websocket.sent[-1], '{"type": "tts"}')

    async def test_offline_device_falls_back(self):
        srv = server()
        web = handler("AA", web=True)
        web.server = srv
        srv.register_connection(web)
        srv.register_connection(handler("AA", ready=False))
        with patch.object(listen, "startToChat", new_callable=AsyncMock) as chat:
            routed = await listen.route_text_to_device(web, "hi")
        self.assertFalse(routed)
        chat.assert_not_awaited()
        self.assertEqual(json.loads(web.websocket.sent[-1])["state"], "device_offline")

    async def test_broken_mirror_is_dropped(self):
        device = handler("AA")
        broken = FakeHandler(websocket=SimpleNamespace(send=AsyncMock(side_effect=OSError("closed"))))
        device.mirror_connections.add(broken)
        await sendAudioHandle._send_to_mirrors(device, "x")
        self.assertNotIn(broken, device.mirror_connections)


if __name__ == "__main__":
    unittest.main()
