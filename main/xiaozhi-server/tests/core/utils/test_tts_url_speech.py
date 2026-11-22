from core.utils.tts import MarkdownCleaner


def test_speech_keeps_markdown_link_label_but_removes_target_url():
    spoken = MarkdownCleaner.clean_markdown("來源：[官方公告](https://example.org/news?id=7)。")
    assert spoken == "來源：官方公告。"
    assert "https://" not in spoken


def test_speech_does_not_spell_bare_or_www_urls():
    spoken = MarkdownCleaner.clean_markdown("請看 https://example.org/page?q=1，或 www.example.net/docs。")
    assert "https://" not in spoken
    assert "www." not in spoken
    assert spoken == "請看，或。"


def test_regular_text_is_preserved():
    assert MarkdownCleaner.clean_markdown("這是正常的口語回答。") == "這是正常的口語回答。"
