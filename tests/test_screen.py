# tests/test_screen.py
import pytest
import mss

from vision import screen


def _has_display() -> bool:
    try:
        with mss.MSS() as sct:
            sct.grab(sct.monitors[1])
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_display(), reason="no screen/display available for capture")


def test_capture_jpeg_returns_jpeg_bytes():
    data = screen.capture_jpeg()
    assert isinstance(data, bytes)
    assert data[:3] == b"\xff\xd8\xff"  # magic bytes JPEG
