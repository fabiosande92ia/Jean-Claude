import os

import pytest

from core import config
from voice import tts

_voice = config.PROJECT_ROOT / "models" / "pt_PT-tugao-medium.onnx"
pytestmark = pytest.mark.skipif(not _voice.exists(), reason="Piper voice model not present")


def test_synth_creates_wav(tmp_path):
    engine = tts.get_tts()
    out = str(tmp_path / "out.wav")
    path = engine.synth("olá Fábio, sou o Jean Claude", out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


def test_get_tts_returns_tts_instance():
    assert isinstance(tts.get_tts(), tts.TTS)
