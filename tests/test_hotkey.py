import numpy as np
import soundfile as sf
from voice import hotkey


def test_save_wav_writes_file(tmp_path):
    """Test that save_wav writes a readable WAV file with correct properties."""
    frames = np.zeros((16000, 1), dtype="float32")
    out = str(tmp_path / "rec.wav")
    path = hotkey.save_wav(frames, 16000, out)
    data, sr = sf.read(path)
    assert sr == 16000
    assert len(data) == 16000


class _FakeStream:
    """Stub de sd.InputStream para testar Recorder sem hardware de áudio."""

    def __init__(self, *args, callback=None, **kwargs):
        self.callback = callback

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


def test_recorder_start_sets_active(monkeypatch):
    monkeypatch.setattr(hotkey.sd, "InputStream", _FakeStream)
    rec = hotkey.Recorder(samplerate=16000)
    assert rec.active is False
    rec.start()
    assert rec.active is True


def test_recorder_start_twice_is_noop(monkeypatch):
    monkeypatch.setattr(hotkey.sd, "InputStream", _FakeStream)
    rec = hotkey.Recorder(samplerate=16000)
    rec.start()
    first_stream = rec._stream
    rec.start()
    assert rec._stream is first_stream


def test_recorder_stop_without_start_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(hotkey.sd, "InputStream", _FakeStream)
    rec = hotkey.Recorder(samplerate=16000)
    out = str(tmp_path / "rec.wav")
    assert rec.stop(out) is None


def test_recorder_stop_writes_silence_when_no_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(hotkey.sd, "InputStream", _FakeStream)
    rec = hotkey.Recorder(samplerate=16000)
    rec.start()
    out = str(tmp_path / "rec.wav")
    path = rec.stop(out)
    assert path == out
    assert rec.active is False
    data, sr = sf.read(path)
    assert sr == 16000
    assert len(data) >= 1
