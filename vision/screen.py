# vision/screen.py
import io
import mss
from PIL import Image


def capture_png() -> bytes:
    """Captura o ecrã principal e devolve PNG em bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # monitor principal
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
