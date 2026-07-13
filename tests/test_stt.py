# tests/test_stt.py
from voice import stt


def test_transcribe_returns_string():
    result = stt.transcribe_file("tests/assets/hello_pt.wav")
    assert isinstance(result, str)
