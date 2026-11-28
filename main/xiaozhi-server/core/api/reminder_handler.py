import os
import re
import time

import aiohttp
from aiohttp import web

from core import reminders

AUDIO_NAME = re.compile(r"^[0-9a-f]{32}\.ogg$")


class ReminderHandler:
    def __init__(self, service, manager_url=""):
        self.service = service
        self.manager_url = manager_url.rstrip("/")
        self.valid_tokens = {}

    def routes(self):
        return [
            web.get("/reminders", self.page),
            web.get("/reminders/", self.page),
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
                async with session.get(f"{self.manager_url}/user/info", headers={"Authorization": auth}) as resp:
                    data = await resp.json(content_type=None)
        except Exception:
            return False
        if data.get("code") == 0 and data.get("data"):
            self.valid_tokens = {k: v for k, v in self.valid_tokens.items() if v > now}
            self.valid_tokens[auth] = now + 60
            return True
        return False

    @web.middleware
    async def middleware(self, request, handler):
        if request.path.startswith("/reminders/api/") and not await self.authorized(request):
            return web.json_response({"error": "請先登入智控台"}, status=401)
        return await handler(request)

    async def page(self, request):
        raise web.HTTPFound("/#/reminders")

    async def list_items(self, request):
        return web.json_response({"items": reminders.list_reminders(), "device": reminders.DEVICE_MAC})

    async def create_item(self, request):
        try:
            item = reminders.create_reminder(await request.json())
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response(item, status=201)

    async def update_item(self, request):
        try:
            item = reminders.update_reminder(int(request.match_info["id"]), await request.json())
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        if item is None:
            return web.json_response({"error": "找不到提醒"}, status=404)
        return web.json_response(item)

    async def delete_item(self, request):
        if not reminders.delete_reminder(int(request.match_info["id"])):
            return web.json_response({"error": "找不到提醒"}, status=404)
        return web.json_response({"ok": True})

    async def test(self, request):
        data = await request.json()
        text = str(data.get("text", "")).strip()[:200]
        if not text:
            return web.json_response({"error": "請輸入內容"}, status=400)
        return web.json_response({"status": await self.service.deliver(text)})

    async def audio(self, request):
        name = request.match_info["name"]
        path = os.path.join(reminders.AUDIO_DIR, name)
        if not AUDIO_NAME.match(name) or not os.path.isfile(path):
            raise web.HTTPNotFound()
        with open(path, "rb") as f:
            body = f.read()
        return web.Response(body=body, content_type="audio/ogg")
