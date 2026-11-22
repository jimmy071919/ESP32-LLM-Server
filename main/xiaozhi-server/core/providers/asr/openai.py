import time
import os
import asyncio
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

import requests

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")        
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file
        # 可選：指定語言（ISO-639-1，例如 zh、en）與提示詞。
        # Whisper 的 prompt 可引導輸出用字，例如以繁體中文提示詞讓轉寫偏向繁體。
        self.language = (config.get("language") or "").strip()
        self.prompt = (config.get("prompt") or "").strip()
        try:
            self.timeout = float(config.get("timeout") or 30)
        except (TypeError, ValueError):
            self.timeout = 30.0

        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, artifacts=None) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            if artifacts is None:
                return "", None
            file_path = artifacts.file_path
                
            logger.bind(tag=TAG).info(f"file path: {file_path}")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            
            # 使用data参数传递模型名称
            data = {
                "model": self.model
            }
            if self.language:
                data["language"] = self.language
            if self.prompt:
                data["prompt"] = self.prompt

            def _post():
                with open(file_path, "rb") as audio_file:  # 使用with语句确保文件关闭
                    return requests.post(
                        self.api_url,
                        files={"file": audio_file},
                        data=data,
                        headers=headers,
                        timeout=self.timeout,
                    )

            start_time = time.time()
            # 在執行緒中送出，避免阻塞 WebSocket 事件迴圈
            response = await asyncio.to_thread(_post)
            logger.bind(tag=TAG).debug(
                f"语音识别耗时: {time.time() - start_time:.3f}s | status: {response.status_code}"
            )

            if response.status_code == 200:
                text = response.json().get("text", "")
                return text, file_path
            else:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
        
