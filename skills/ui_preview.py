# skills/ui_preview.py
"""
Lança só a UI, sem worker/modelos. Para inspeção visual e screenshots.

    python -m skills.ui_preview [estado]

Injeta histórico falso e um estado fixo. Nada de Whisper, nada de TTS.
"""
import math
import queue
import sys
import threading
import time
from datetime import datetime, timedelta

from ui import app as ui_app


def _historico():
    agora = datetime.now()
    def ts(min_atras):
        return (agora - timedelta(minutes=min_atras)).isoformat()
    return [
        {"role": "user", "text": "abre o spotify", "ts": ts(9)},
        {"role": "assistant", "text": "Spotify aberto.", "ts": ts(9)},
        {"role": "user", "text": "que temperatura tem a gpu?", "ts": ts(6)},
        {"role": "assistant",
         "text": "RTX 3060 a 47C, idle. Ventoinhas a 30%. Nada a arder.",
         "ts": ts(6)},
        {"role": "error", "text": "TimeoutError: modelo nao respondeu em 30s", "ts": ts(4)},
        {"role": "user",
         "text": "resume-me o que fizemos hoje no projeto, com detalhe, porque quero "
                 "escrever no diario de bordo e nao me lembro de metade das coisas",
         "ts": ts(2)},
        {"role": "assistant",
         "text": "Hoje: (1) StateBus a derivar estado sob lock, adeus label a mentir. "
                 "(2) cancelamento real via asyncio task. (3) VU meter no topo. "
                 "(4) entrada de texto que salta o STT. (5) tray opcional.",
         "ts": ts(2)},
    ]


def main():
    estado = sys.argv[1] if len(sys.argv) > 1 else "idle"
    ui_queue: "queue.Queue" = queue.Queue()
    tts_enabled = threading.Event()
    tts_enabled.set()

    def feeder():
        time.sleep(0.4)
        ui_queue.put(("state", estado))

        # Corrida de consola falsa: dá para ver a aba, o badge a girar e o botão
        # de reiniciar sem precisar de um ConsoleRunner a sério.
        ui_queue.put(("consola_estado", {"run": True, "modelo": "opus"}))
        for linha in ["vou editar o agente", "🔧 Edit: brain/agent.py", "🔧 Bash: pytest",
                      "— consola terminou —"]:
            time.sleep(0.6)
            ui_queue.put(("consola", linha))
        time.sleep(0.4)
        ui_queue.put(("consola_estado", {"run": False}))
        ui_queue.put(("consola_fim", "mudei o agente, testes passaram"))

        t = 0.0
        while True:                      # VU vivo, para ver a barra a mexer
            if estado == "recording":
                ui_queue.put(("level", abs(math.sin(t)) * 0.09))
            t += 0.15
            time.sleep(0.05)

    threading.Thread(target=feeder, daemon=True).start()

    ui_app.launch(
        on_press=lambda: ui_queue.put(("state", "recording")),
        on_release=lambda: ui_queue.put(("state", "idle")),
        ui_queue=ui_queue,
        on_close=lambda: None,
        tts_enabled=tts_enabled,
        on_text=lambda t: ui_queue.put(("user", t)),
        on_cancel=lambda: ui_queue.put(("info", "parado.")),
        hotkey_label="ctrl+space",
        historico=_historico(),
        on_reiniciar=lambda: ui_queue.put(("info", "reiniciar (preview)")),
    )


if __name__ == "__main__":
    main()
