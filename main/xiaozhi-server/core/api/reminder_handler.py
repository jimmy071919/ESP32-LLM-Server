import asyncio
import os
import re
import time
from urllib.parse import quote

import aiohttp
from aiohttp import web

from core import reminders

AUDIO_NAME = re.compile(r"^[0-9a-f]{32}\.ogg$")


class ReminderHandler:
    def __init__(self, service, manager_url=""):
        self.service = service
        self.manager_url = manager_url.rstrip("/")
        self.valid_tokens = {}
        self.device_cache = {}

    def routes(self):
        return [
            web.get("/reminders", self.page),
            web.get("/reminders/", self.page),
            web.get("/reminders/api/devices", self.list_devices),
            web.get("/reminders/api/items", self.list_items),
            web.post("/reminders/api/items", self.create_item),
            web.put("/reminders/api/items/{id}", self.update_item),
            web.delete("/reminders/api/items/{id}", self.delete_item),
            web.post("/reminders/api/test", self.test),
            web.get("/reminders/audio/{name}", self.audio),
        ]

    async def authorized(self, request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not self.manager_url:
            return False
        now = time.time()
        if self.valid_tokens.get(auth, 0) > now:
            return True
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(
                    f"{self.manager_url}/user/info", headers={"Authorization": auth}
                ) as resp:
                    data = await resp.json(content_type=None)
        except Exception:
            return False
        if isinstance(data, dict) and data.get("code") == 0 and data.get("data"):
            self.valid_tokens = {k: v for k, v in self.valid_tokens.items() if v > now}
            self.valid_tokens[auth] = now + 60
            return True
        return False

    @web.middleware
    async def middleware(self, request, handler):
        if request.path.startswith("/reminders/api/") and not await self.authorized(request):
            return web.json_response({"error": "請先登入智控台"}, status=401)
        return await handler(request)

    async def fetch_manager_json(self, session, path, auth):
        async with session.get(f"{self.manager_url}{path}", headers={"Authorization": auth}) as resp:
            data = await resp.json(content_type=None)
        if not isinstance(data, dict) or data.get("code") != 0:
            raise RuntimeError("無法取得已綁定裝置")
        return data.get("data")

    async def user_devices(self, auth):
        now = time.time()
        cached = self.device_cache.get(auth)
        if cached and cached[0] > now:
            return cached[1]
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            agents = await self.fetch_manager_json(session, "/agent/list", auth)
            if not isinstance(agents, list):
                raise RuntimeError("無法取得智能體列表")

            async def devices_for(agent):
                agent_id = agent.get("id")
                if not agent_id:
                    return []
                devices = await self.fetch_manager_json(
                    session, f"/device/bind/{quote(str(agent_id), safe='')}", auth
                )
                if not isinstance(devices, list):
                    return []
                return [(agent, device) for device in devices]

            results = await asyncio.gather(*(devices_for(agent) for agent in agents))
        found = {}
        for items in results:
            for agent, device in items:
                mac = str(device.get("macAddress") or "").strip().lower()
                if not mac:
                    continue
                found[mac] = {
                    "macAddress": mac,
                    "alias": device.get("alias") or "",
                    "board": device.get("board") or "",
                    "agentName": agent.get("agentName") or "",
                    "online": mac in reminders.notify_channels or mac in reminders.active_connections,
                }
        devices = sorted(
            found.values(),
            key=lambda item: (item["alias"] or item["agentName"] or item["board"], item["macAddress"]),
        )
        self.device_cache[auth] = (now + 60, devices)
        return devices

    async def resolve_device(self, request, device_mac):
        auth = request.headers.get("Authorization", "")
        normalized = str(device_mac or "").strip().lower()
        if not normalized:
            raise ValueError("請選擇提醒裝置")
        devices = await self.user_devices(auth)
        if not any(device["macAddress"] == normalized for device in devices):
            raise PermissionError("無法使用這台裝置")
        return normalized

    async def page(self, request):
        raise web.HTTPFound("/#/reminders")

    async def list_devices(self, request):
        try:
            devices = await self.user_devices(request.headers["Authorization"])
        except Exception:
            return web.json_response({"error": "無法取得已綁定裝置"}, status=502)
        default_device = reminders.DEFAULT_DEVICE_MAC
        if not any(device["macAddress"] == default_device for device in devices):
            default_device = devices[0]["macAddress"] if len(devices) == 1 else ""
        return web.json_response({"devices": devices, "default_device": default_device})

    async def list_items(self, request):
        try:
            device_mac = await self.resolve_device(request, request.query.get("device_mac"))
        except (ValueError, PermissionError) as e:
            return web.json_response({"error": str(e)}, status=403)
        except Exception:
            return web.json_response({"error": "無法取得已綁定裝置"}, status=502)
        return web.json_response({"items": reminders.list_reminders(device_mac), "device": device_mac})

    async def create_item(self, request):
        try:
            data = await request.json()
            data["device_mac"] = await self.resolve_device(request, data.get("device_mac"))
            item = reminders.create_reminder(data)
        except PermissionError as e:
            return web.json_response({"error": str(e)}, status=403)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response(item, status=201)

    async def update_item(self, request):
        try:
            device_mac = await self.resolve_device(request, request.query.get("device_mac"))
            item = reminders.update_reminder(
                int(request.match_info["id"]), await request.json(), device_mac
            )
        except PermissionError as e:
            return web.json_response({"error": str(e)}, status=403)
        except RuntimeError as e:
            return web.json_response({"error": str(e)}, status=502)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        if item is None:
            return web.json_response({"error": "找不到提醒"}, status=404)
        return web.json_response(item)

    async def delete_item(self, request):
        try:
            device_mac = await self.resolve_device(request, request.query.get("device_mac"))
        except (ValueError, PermissionError) as e:
            return web.json_response({"error": str(e)}, status=403)
        except Exception:
            return web.json_response({"error": "無法取得已綁定裝置"}, status=502)
        if not reminders.delete_reminder(int(request.match_info["id"]), device_mac):
            return web.json_response({"error": "找不到提醒"}, status=404)
        return web.json_response({"ok": True})

    async def test(self, request):
        data = await request.json()
        try:
            device_mac = await self.resolve_device(request, data.get("device_mac"))
        except (ValueError, PermissionError) as e:
            return web.json_response({"error": str(e)}, status=403)
        except Exception:
            return web.json_response({"error": "無法取得已綁定裝置"}, status=502)
        text = str(data.get("text", "")).strip()[:200]
        if not text:
            return web.json_response({"error": "請輸入內容"}, status=400)
        return web.json_response({"status": await self.service.deliver(device_mac, text)})

    async def audio(self, request):
        name = request.match_info["name"]
        path = os.path.join(reminders.AUDIO_DIR, name)
        if not AUDIO_NAME.match(name) or not os.path.isfile(path):
            raise web.HTTPNotFound()
        with open(path, "rb") as f:
            body = f.read()
        return web.Response(body=body, content_type="audio/ogg")
