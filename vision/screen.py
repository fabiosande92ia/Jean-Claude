# vision/screen.py
import io
import mss
from PIL import Image

MAX_DIMENSION = 1568  # acima disto o Claude reamostra a imagem de qualquer forma
JPEG_QUALITY = 70


def capture_jpeg() -> bytes:
    """Captura o ecrã principal e devolve JPEG em bytes.

    O SDK do agente lê a resposta da tool inteira numa única linha JSON com um
    buffer fixo de 1MB. Um PNG de ecrã inteiro em base64 estoura isso e a
    transport falha com "JSON message exceeded maximum buffer size". Reduz
    resolução e usa JPEG para o payload ficar sempre bem abaixo do limite.
    """
    with mss.MSS() as sct:
        monitor = sct.monitors[1]  # monitor principal
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()
