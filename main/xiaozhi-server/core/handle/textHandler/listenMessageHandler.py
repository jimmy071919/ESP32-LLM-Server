import json
import time
import uuid
import asyncio
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.utils.dialogue import Message
from core.providers.asr.dto.dto import InterfaceType
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.handle.sendAudioHandle import send_stt_message, send_tts_message
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.utils.util import remove_punctuation_and_length
from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType


TAG = __name__

class ListenTextMessageHandler(TextMessageHandler):
    """Listen消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.LISTEN

    async def handle(self, conn: "ConnectionHandler", msg_json: Dict[str, Any]) -> None:
        if "mode" in msg_json:
            conn.client_listen_mode = msg_json["mode"]
            conn.logger.bind(tag=TAG).debug(
                f"客户端拾音模式：{conn.client_listen_mode}"
            )
        if msg_json["state"] == "start":
            # 设备从播放模式切回录音模式,清除所有音频状态和缓冲区
            conn.reset_audio_states()
        elif msg_json["state"] == "stop":
            # 收到stop但asr未初始化，跳过处理
            if conn.asr is None:
                return

            conn.client_voice_stop = True
            if conn.asr.interface_type == InterfaceType.STREAM:
                # 流式模式下，发送结束请求
                asyncio.create_task(conn.asr._send_stop_request())
            else:
                # 非流式模式：直接触发ASR识别
                if len(conn.asr_audio) > 0:
                    asr_audio_task = conn.asr_audio.copy()
                    conn.reset_audio_states()

                    if len(asr_audio_task) > 0:
                        await conn.asr.handle_voice_stop(conn, asr_audio_task)
        elif msg_json["state"] == "detect":
            conn.client_have_voice = False
            conn.reset_audio_states()
            if "text" in msg_json:
                conn.last_activity_time = time.time() * 1000
                original_text = msg_json["text"]  # 保留原始文本
                filtered_len, filtered_text = remove_punctuation_and_length(
                    original_text
                )

                # 检查是否是设备呼叫指令 [device_call]
                if original_text.startswith("[device_call]"):
                    # 提取 tag 后的文本
                    call_text = original_text[len("[device_call]"):].strip()
                    conn.logger.bind(tag=TAG).info(f"收到设备呼叫指令: {call_text}")

                    # 标记为来电接听模式
                    conn.incoming_call = True

                    # 准备开始新会话
                    conn.sentence_id = uuid.uuid4().hex

                    await send_stt_message(conn, call_text)

                    # 等待tts初始化，最多等待3秒
                    start_time = time.time()
                    while time.time() - start_time < 3:
                        if conn.tts:
                            break
                        await asyncio.sleep(0.1)

                    if conn.tts:
                        conn.tts.store_tts_text(conn.sentence_id, call_text)
                        conn.tts.tts_text_queue.put(TTSMessageDTO(sentence_id=conn.sentence_id, sentence_type=SentenceType.FIRST, content_type=ContentType.ACTION))
                        conn.tts.tts_one_sentence(conn, ContentType.TEXT, content_detail=call_text)
                        conn.tts.tts_text_queue.put(TTSMessageDTO(sentence_id=conn.sentence_id, sentence_type=SentenceType.LAST, content_type=ContentType.ACTION))

                    # 添加到对话历史，让模型理解上下文
                    conn.dialogue.put(Message(role="assistant", content=call_text))
                    return

                # 识别是否是唤醒词
                is_wakeup_words = filtered_text in conn.config.get("wakeup_words")
                # 是否开启唤醒词回复
                enable_greeting = conn.config.get("enable_greeting", True)

                if is_wakeup_words and not enable_greeting:
                    # 如果是唤醒词，且关闭了唤醒词回复，就不用回答
                    await send_stt_message(conn, original_text)
                    await send_tts_message(conn, "stop", None)
                    conn.client_is_speaking = False
                elif is_wakeup_words:
                    conn.just_woken_up = True
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, "嘿，你好呀", [])
                    await startToChat(conn, "嘿，你好呀")
                else:
                    # 工作台要求由實體裝置說出 AI 的回答
                    if conn.web_chat_mode and msg_json.get("speak_on_device"):
                        if await route_text_to_device(conn, original_text):
                            return
                    conn.just_woken_up = True
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, original_text, [])
                    # 否则需要LLM对文字内容进行答复
                    await startToChat(conn, original_text)


async def route_text_to_device(conn: "ConnectionHandler", text: str) -> bool:
    """把工作台輸入的文字交給同一台實體裝置的連線處理，讓裝置播出 AI 的回答。

    回覆文字（tts sentence_start／stop）會同步回工作台。裝置未連線或尚未初始化完成時回傳 False，
    並通知工作台改為只顯示文字。
    """
    server = getattr(conn, "server", None)
    finder = getattr(server, "find_device_connection", None)
    device_conn = finder(conn.device_id, exclude=conn) if finder else None
    if device_conn is None or device_conn.tts is None or device_conn.llm is None:
        await conn.websocket.send(
            json.dumps({"type": "web_chat", "state": "device_offline", "session_id": conn.session_id})
        )
        return False

    device_conn.mirror_connections.add(conn)
    device_conn.last_activity_time = time.time() * 1000
    device_conn.just_woken_up = True
    conn.logger.bind(tag=TAG).info(f"工作台文字交由裝置 {conn.device_id} 回答並播放")
    await conn.websocket.send(
        json.dumps({"type": "web_chat", "state": "device_routed", "session_id": conn.session_id})
    )
    enqueue_asr_report(device_conn, text, [])
    await startToChat(device_conn, text)
    return True
