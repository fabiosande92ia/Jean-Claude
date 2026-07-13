# main.py
import asyncio
import queue
import tempfile
import threading
import uuid
from collections import deque
from pathlib import Path
from core import config
from brain.agent import JeanClaude
from brain import memory
from voice import stt, tts, hotkey
from ui import app as ui_app

HISTORY_SIZE = 5


def new_rec_path() -> str:
    # Temp do SO, não a raiz do repo: se crashar antes do unlink, o lixo não fica no projeto.
    return str(Path(tempfile.gettempdir()) / f"_jc_rec_{uuid.uuid4().hex}.wav")


class StateBus:
    """
    Fonte única de verdade do estado.

    O UI não pode receber estados soltos de várias threads (hotkey e worker) — o
    `idle` atrasado de um job antigo chegava depois do `recording` do job novo e a
    label mentia. Aqui o estado é *derivado* de todos os factos sob um lock, e só
    emite quando muda.
    """

    def __init__(self, ui_queue: "queue.Queue"):
        self.ui_queue = ui_queue
        self._lock = threading.Lock()
        self._pending = 0
        self._recording = False
        self._speaking = False
        self._ready = False
        self._last = None
        self._emit()   # arranque honesto: "a carregar modelos", não "idle"

    def _derive(self) -> str:
        if self._recording:
            return "recording"
        if self._pending:
            return "processing"
        if not self._ready:
            return "loading"
        if self._speaking:
            return "speaking"
        return "idle"

    def _emit(self) -> None:
        state = self._derive()
        if state != self._last:
            self._last = state
            self.ui_queue.put(("state", state))

    def _set(self, **facts) -> None:
        with self._lock:
            for k, v in facts.items():
                setattr(self, f"_{k}", v)
            self._emit()

    def recording(self, on: bool) -> None:
        self._set(recording=on)

    def speaking(self, on: bool) -> None:
        self._set(speaking=on)

    def ready(self) -> None:
        self._set(ready=True)

    def job_start(self) -> None:
        with self._lock:
            self._pending += 1
            self._emit()

    def job_done(self, speaking: bool = False) -> None:
        # `speaking` entra na mesma transição: fechar o job e abrir a fala em dois
        # passos separados piscava "idle" entre eles.
        with self._lock:
            self._pending = max(0, self._pending - 1)
            self._speaking = speaking
            self._emit()


def build_prompt(index: str, history: "deque", texto: str) -> str:
    historico = ""
    if history:
        trocas = "\n\n".join(f"Fábio: {u}\nJean Claude: {a}" for u, a in history)
        historico = f"[conversa recente]\n{trocas}\n\n"
    return f"[memória índice]\n{index}\n\n{historico}[Fábio disse]\n{texto}"


def worker_loop(rec_queue: "queue.Queue", ui_queue: "queue.Queue", state: StateBus, stop_event: threading.Event, tts_enabled: threading.Event):
    try:
        jc = JeanClaude()
        index = memory.read_index()
        history = deque(maxlen=HISTORY_SIZE)
    except Exception as e:
        ui_queue.put(("error", f"Falha a iniciar o worker (agente/memória): {e}"))
        state.ready()
        return

    try:
        speaker = tts.get_tts()
    except Exception as e:
        ui_queue.put(("error", f"Falha a carregar a voz Piper: {e}"))
        speaker = None

    # O Whisper large-v3 é lazy: carregava só na 1ª transcrição (30-60s de silêncio
    # com a UI a dizer "idle"). Carrega já, e o estado diz "a carregar modelos".
    try:
        stt.get_model()
    except Exception as e:
        ui_queue.put(("error", f"Falha a carregar o Whisper: {e}"))
    state.ready()

    while not stop_event.is_set():
        try:
            wav_path = rec_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if wav_path is None:
            break
        resposta = None
        try:
            texto = stt.transcribe_file(wav_path)
            if texto.strip():
                ui_queue.put(("user", texto))
                resposta = asyncio.run(jc.ask(build_prompt(index, history, texto)))
                ui_queue.put(("assistant", resposta))
                history.append((texto, resposta))
        except Exception as e:
            ui_queue.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            Path(wav_path).unlink(missing_ok=True)
            vai_falar = bool(resposta and speaker and tts_enabled.is_set())
            state.job_done(speaking=vai_falar)

        # Fora do job: falar não é "a processar". Estado passa a "a falar".
        if vai_falar:
            try:
                speaker.speak(resposta)
            except Exception as e:
                ui_queue.put(("error", f"TTS: {type(e).__name__}: {e}"))
            finally:
                state.speaking(False)


def main():
    ui_queue: "queue.Queue" = queue.Queue()
    rec_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    tts_enabled = threading.Event()
    tts_enabled.set()
    recorder = hotkey.Recorder()
    state = StateBus(ui_queue)

    def begin_recording():
        recorder.start()
        state.recording(True)

    def end_recording():
        path = recorder.stop(new_rec_path())
        if path:
            state.job_start()   # conta o job *antes* de baixar recording: nunca pisca "idle"
            rec_queue.put(path)
        state.recording(False)

    global_hotkey = hotkey.GlobalHotkey(hotkey.NUMPAD_MINUS, begin_recording, end_recording)
    global_hotkey.start()

    worker = threading.Thread(target=worker_loop, args=(rec_queue, ui_queue, state, stop_event, tts_enabled), daemon=True)
    worker.start()

    def on_close():
        stop_event.set()
        rec_queue.put(None)
        global_hotkey.stop()

    ui_app.launch(begin_recording, end_recording, ui_queue, on_close, tts_enabled)


if __name__ == "__main__":
    main()
