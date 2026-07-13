# main.py
import asyncio
import queue
import threading
import uuid
from pathlib import Path
from core import config
from brain.agent import JeanClaude
from brain import memory
from voice import stt, tts, hotkey
from ui import app as ui_app


def new_rec_path() -> str:
    return str(config.PROJECT_ROOT / f"_jc_rec_{uuid.uuid4().hex}.wav")


def build_prompt(index: str, texto: str) -> str:
    return f"[memória índice]\n{index}\n\n[Fábio disse]\n{texto}"


def worker_loop(rec_queue: "queue.Queue", ui_queue: "queue.Queue", stop_event: threading.Event):
    try:
        jc = JeanClaude()
        index = memory.read_index()
    except Exception as e:
        ui_queue.put(("error", f"Falha a iniciar o worker (agente/memória): {e}"))
        ui_queue.put(("state", "idle"))
        return

    try:
        speaker = tts.get_tts()
    except Exception as e:
        ui_queue.put(("error", f"Falha a carregar a voz Piper: {e}"))
        speaker = None

    while not stop_event.is_set():
        try:
            wav_path = rec_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if wav_path is None:
            break
        try:
            texto = stt.transcribe_file(wav_path)
            if not texto.strip():
                continue
            ui_queue.put(("user", texto))
            resposta = asyncio.run(jc.ask(build_prompt(index, texto)))
            ui_queue.put(("assistant", resposta))
            if speaker:
                speaker.speak(resposta)
        except Exception as e:
            ui_queue.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            Path(wav_path).unlink(missing_ok=True)
            ui_queue.put(("state", "idle"))


def main():
    ui_queue: "queue.Queue" = queue.Queue()
    rec_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    recorder = hotkey.Recorder()

    def begin_recording():
        recorder.start()
        ui_queue.put(("state", "recording"))

    def end_recording():
        path = recorder.stop(new_rec_path())
        if path:
            ui_queue.put(("state", "processing"))
            rec_queue.put(path)
        else:
            ui_queue.put(("state", "idle"))

    global_hotkey = hotkey.GlobalHotkey(hotkey.NUMPAD_MINUS, begin_recording, end_recording)
    global_hotkey.start()

    worker = threading.Thread(target=worker_loop, args=(rec_queue, ui_queue, stop_event), daemon=True)
    worker.start()

    def on_close():
        stop_event.set()
        rec_queue.put(None)
        global_hotkey.stop()

    ui_app.launch(begin_recording, end_recording, ui_queue, on_close)


if __name__ == "__main__":
    main()
