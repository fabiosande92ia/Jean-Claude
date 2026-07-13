import importlib.util
import os

import numpy as np
import pytest

from core import config
from voice import tts


def test_engines_are_tts_subclasses():
    # Estrutural: não instancia (edge_vc/xtts carregam torch + modelos).
    for cls in (tts.EdgeTTS, tts.EdgeVcTTS, tts.XttsTTS):
        assert issubclass(cls, tts.TTS)


def test_default_engine_is_edge_vc():
    assert config.TTS_ENGINE == "edge_vc"
    assert config.EDGE_VOICE == "pt-PT-DuarteNeural"   # PT-PT europeu


def test_speaker_wav_configured():
    assert str(config.XTTS_SPEAKER_WAV).endswith(".wav")


# --- robotize (puro numpy, sem rede) ----------------------------------------

def _tone(sr=16000, secs=0.25, hz=200.0):
    t = np.arange(int(sr * secs), dtype=np.float32) / sr
    return (0.5 * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def test_robot_preset_B_thin():
    assert config.TTS_ROBOT is True
    assert config.TTS_ROBOT_CARRIER_HZ == 140.0
    assert config.TTS_ROBOT_CRUSH_BITS == 7
    assert config.TTS_ROBOT_PITCH_SEMITONES == 6.0   # voz fina


def test_robotize_pitch_preserva_forma():
    sig = _tone()
    out = tts.robotize(sig, 16000, pitch_semitones=6.0)
    assert out.shape == sig.shape       # pitch shift mantém a duração
    assert out.dtype == np.float32


def test_robotize_preserva_forma_e_tipo():
    sig = _tone()
    out = tts.robotize(sig, 16000)
    assert out.shape == sig.shape
    assert out.dtype == np.float32


def test_robotize_dentro_do_range():
    sig = _tone() * 5.0   # força clipping
    out = tts.robotize(sig, 16000)
    assert out.max() <= 1.0 and out.min() >= -1.0


def test_robotize_mix_zero_e_identidade():
    sig = _tone()
    out = tts.robotize(sig, 16000, mix=0.0)
    assert np.allclose(out, sig, atol=1e-6)   # dry puro = voz intacta


def test_robotize_altera_com_mix_alto():
    sig = _tone()
    out = tts.robotize(sig, 16000, mix=1.0, carrier_hz=55.0, crush_bits=6)
    assert not np.allclose(out, sig, atol=1e-3)   # robô mesmo mudou o sinal


def test_robotize_estereo():
    sig = np.stack([_tone(), _tone()], axis=1)   # (n, 2)
    out = tts.robotize(sig, 16000)
    assert out.shape == sig.shape


_have_edge = importlib.util.find_spec("edge_tts") is not None


@pytest.mark.skipif(
    not (os.environ.get("JC_TEST_TTS") and _have_edge),
    reason="Edge-TTS é online; correr só com JC_TEST_TTS=1",
)
def test_edge_synth_creates_wav(tmp_path):
    engine = tts.EdgeTTS()
    out = str(tmp_path / "out.wav")
    path = engine.synth("olá Fábio, sou o Jean Claude", out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0
