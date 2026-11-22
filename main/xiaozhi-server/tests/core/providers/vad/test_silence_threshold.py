from unittest.mock import patch

from core.providers.vad.silero import VADProvider


def _provider(min_silence_duration_ms):
    config = {
        "model_dir": "/unused",
        "min_silence_duration_ms": str(min_silence_duration_ms),
    }
    with patch("core.providers.vad.silero.onnxruntime.InferenceSession", return_value=object()):
        return VADProvider(config)


def test_auto_listen_has_two_second_silence_floor():
    assert _provider(700).silence_threshold_ms == 2000


def test_longer_vad_setting_is_preserved():
    assert _provider(2500).silence_threshold_ms == 2500
