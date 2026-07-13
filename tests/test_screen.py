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


def test_capture_png_returns_png_bytes():
    data = screen.capture_png()
    assert isinstance(data, bytes)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # magic bytes PNG
