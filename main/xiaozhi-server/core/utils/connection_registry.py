"""記錄每台裝置目前在線的 WebSocket 連線（實體裝置與工作台 web-chat 連線）。"""


class ConnectionRegistry:
    def __init__(self):
        self.device_connections = {}

    def register(self, handler) -> None:
        device_id = getattr(handler, "device_id", None)
        if device_id:
            self.device_connections.setdefault(device_id, set()).add(handler)

    def unregister(self, handler) -> None:
        device_id = getattr(handler, "device_id", None)
        handlers = self.device_connections.get(device_id)
        if handlers is not None:
            handlers.discard(handler)
            if not handlers:
                self.device_connections.pop(device_id, None)
        # 工作台斷線時，不再把裝置回覆同步給它
        for others in list(self.device_connections.values()):
            for other in others:
                getattr(other, "mirror_connections", set()).discard(handler)

    def find_device_connection(self, device_id, exclude=None):
        """找出同一台裝置的實體連線（非工作台），已初始化完成者優先、最新者優先。"""
        candidates = [
            handler
            for handler in self.device_connections.get(device_id, ())
            if handler is not exclude
            and not getattr(handler, "web_chat_mode", False)
            and getattr(handler, "websocket", None) is not None
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda h: (
                getattr(h, "tts", None) is not None and getattr(h, "llm", None) is not None,
                getattr(h, "first_activity_time", 0) or 0,
            ),
        )
