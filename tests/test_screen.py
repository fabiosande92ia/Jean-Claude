# tests/test_screen.py
from vision import screen

def test_capture_png_returns_png_bytes():
    data = screen.capture_png()
    assert isinstance(data, bytes)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # magic bytes PNG
