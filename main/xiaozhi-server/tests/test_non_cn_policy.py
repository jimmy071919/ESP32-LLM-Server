"""S2 non-China policy gate for the YAML defaults and the active tool code.

This checks *defaults and enabled code paths*, not every adapter that exists:
upstream adapters for Chinese services may remain in the tree but must not be
selected by default or used as hidden fallbacks.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Hosts that the default/active code paths must never contact.
FORBIDDEN_HOSTS = re.compile(
    r"bigmodel\.cn|dashscope|aliyuncs\.com|volces\.com|volcengine|deepseek\.com|"
    r"qweather(api)?\.(com|net)|qweatherapi|metaso\.cn|newsnow\.busiyi|chinanews\.com|pconline\.com\.cn|"
    r"baidu\.com|tencentcloudapi|xfyun\.cn|siliconflow\.cn|minimaxi?\.(com|chat)|coze\.cn|nju\.edu\.cn",
    re.IGNORECASE,
)

CHINESE_MODULES = {
    "ASR": {
        "FunASR", "FunASRServer", "SherpaASR", "SherpaParaformerASR", "DoubaoASR", "DoubaoStreamASR",
        "TencentASR", "AliyunASR", "AliyunStreamASR", "AliyunBLStreamASR", "BaiduASR", "XunfeiStreamASR",
    },
    "LLM": {
        "AliLLM", "AliAppLLM", "DoubaoLLM", "DeepSeekLLM", "ChatGLMLLM", "CozeLLM",
        "VolcesAiGatewayLLM", "XunfeiSparkLLM",
    },
    "VLLM": {"ChatGLMVLLM", "QwenVLVLLM", "XunfeiSparkLLM"},
    "TTS": {
        "DoubaoTTS", "HuoshanDoubleStreamTTS", "CosyVoiceSiliconflow", "CozeCnTTS", "VolcesAiGatewayTTS",
        "MinimaxTTSHTTPStream", "AliyunTTS", "AliyunStreamTTS", "TencentTTS", "AliBLTTS", "XunFeiTTS",
        "PaddleSpeechTTS", "IndexStreamTTS",
    },
}

ACTIVE_CODE = [
    "plugins_func/functions/get_weather.py",
    "plugins_func/functions/get_news_rss.py",
    "plugins_func/functions/web_search.py",
    "core/utils/geolocation.py",
    "core/utils/util.py",
    "core/utils/prompt_manager.py",
]

OTHER_BRAND_WAKE_WORDS = ("小爱同学", "小愛同學", "小冰", "小美同学", "天猫精灵", "小度")


class NonChinaPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

    def test_selected_modules_are_not_chinese_services(self):
        selected = self.config["selected_module"]
        for module_type, forbidden in CHINESE_MODULES.items():
            self.assertNotIn(selected.get(module_type), forbidden, module_type)
            entry = self.config[module_type][selected[module_type]]
            self.assertIsNone(FORBIDDEN_HOSTS.search(str(entry)), f"{module_type}: {entry}")

    def test_helper_llms_are_not_chinese_services(self):
        self.assertNotIn(self.config["Intent"]["intent_llm"]["llm"], CHINESE_MODULES["LLM"])
        self.assertNotIn(self.config["Memory"]["mem_local_short"]["llm"], CHINESE_MODULES["LLM"])
        self.assertIsNone(FORBIDDEN_HOSTS.search(str(self.config["Memory"]["powermem"])))

    def test_plugin_defaults_have_no_forbidden_hosts(self):
        plugins = self.config["plugins"]
        self.assertIsNone(FORBIDDEN_HOSTS.search(str(plugins)), plugins)
        self.assertEqual(plugins["web_search"]["provider"], "tavily")
        self.assertEqual(plugins["get_weather"]["provider"], "openmeteo")
        self.assertFalse(plugins["get_weather"]["default_location"])
        for fn_list in (
            self.config["Intent"]["function_call"]["functions"],
            self.config["Intent"]["intent_llm"]["functions"],
        ):
            self.assertNotIn("get_news_from_newsnow", fn_list)
            self.assertNotIn("get_news_from_chinanews", fn_list)

    def test_geolocation_is_off_by_default(self):
        self.assertEqual(self.config["geolocation"]["provider"], "none")

    def test_no_other_brand_wake_words(self):
        for word in self.config["wakeup_words"]:
            self.assertFalse(any(brand in word for brand in OTHER_BRAND_WAKE_WORDS), word)

    def test_active_tool_code_has_no_forbidden_hosts(self):
        for relative in ACTIVE_CODE:
            text = (ROOT / relative).read_text(encoding="utf-8")
            match = FORBIDDEN_HOSTS.search(text)
            self.assertIsNone(match, f"{relative}: {match and match.group(0)}")

    def test_prompt_has_no_unconditional_weather_claim(self):
        prompt = (ROOT / "agent-base-prompt.txt").read_text(encoding="utf-8")
        self.assertNotIn("The context already provides the local 7-day forecast", prompt)
        self.assertIn("{%- if weather_info %}", prompt)


if __name__ == "__main__":
    unittest.main()
