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
