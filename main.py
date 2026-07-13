# main.py
import asyncio
import contextlib
import queue
import subprocess
import sys
import tempfile
import threading
import uuid
from collections import deque
from pathlib import Path
from core import config
from brain.agent import JeanClaude
from brain import memory, history, router, tools as brain_tools
from voice import stt, tts, hotkey
from ui import app as ui_app


class JobCancelado(Exception):
    """O Fábio carregou em Parar a meio deste job."""


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


class Controls:
    """
    Handles partilhados entre a thread da UI e a do worker.

    Cada job tem o SEU Event de cancel: criado no enqueue (novo_job), removido no
    fim (job_acabou). O Parar faz set a todos os vivos — na fila ou em curso. O
    Event único com clear() no início do job tinha uma race: um Parar entre o
    get() do worker e o clear() era apagado e o job que devia morrer corria todo.

    O `speaker` é escrito pelo worker quando o TTS acaba de carregar e lido pela
    UI: rebind de referência, atómico em CPython — não precisa de lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._vivos: list[threading.Event] = []
        self.speaker = None

    def novo_job(self) -> threading.Event:
        ev = threading.Event()
        with self._lock:
            self._vivos.append(ev)
        return ev

    def job_acabou(self, ev: threading.Event) -> None:
        with self._lock:
            try:
                self._vivos.remove(ev)
            except ValueError:
                pass   # já removido (ex.: drenado pelo cancelar)

    def parar(self) -> None:
        with self._lock:
            for ev in self._vivos:
                ev.set()
            speaker = self.speaker
        if speaker:
            speaker.stop()


def build_prompt(index: str, history_deque: "deque", texto: str) -> str:
    historico = ""
    if history_deque:
        trocas = "\n\n".join(f"Fábio: {u}\nJean Claude: {a}" for u, a in history_deque)
        historico = f"[conversa recente]\n{trocas}\n\n"
    return f"[memória índice]\n{index}\n\n{historico}[Fábio disse]\n{texto}"


async def ask_cancelavel(jc: JeanClaude, prompt: str, cancel: threading.Event, on_delta=None, model=None) -> str:
    """
    Corre jc.ask() mas vigia o `cancel`.

    asyncio.run(jc.ask(...)) era um bloco monolítico: dito o disparate ao mic, havia
    que esperar pelo agente todo. Aqui a pergunta é uma task e o cancel mata-a.
    """
    task = asyncio.create_task(jc.ask(prompt, on_delta=on_delta, model=model))
    while not task.done():
        if cancel.is_set():
            task.cancel()
            with contextlib.suppress(BaseException):
                await task   # deixa a task desenrolar-se (fecha o cliente SDK)
            raise JobCancelado()
        await asyncio.sleep(0.05)
    return task.result()


def _drain_loop(rec_queue: "queue.Queue", ui_queue: "queue.Queue", state: StateBus,
                controls: Controls, stop_event: threading.Event):
    """
    Plano B quando o worker falha o arranque. Morrer sem mais deixava a fila sem
    consumidor: a UI continuava a aceitar jobs e o estado prendia em "a processar"
    para sempre. Aqui cada job é consumido e respondido com erro.
    """
    while not stop_event.is_set():
        try:
            job = rec_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if job is None:
            return
        kind, payload, cancel = job
        if kind == "audio":
            with contextlib.suppress(OSError):
                Path(payload).unlink(missing_ok=True)
        ui_queue.put(("error", "o worker não iniciou — reinicia a app"))
        state.job_done()
        controls.job_acabou(cancel)


def worker_loop(rec_queue: "queue.Queue", ui_queue: "queue.Queue", state: StateBus,
                controls: Controls, stop_event: threading.Event, tts_enabled: threading.Event):
    try:
        jc = JeanClaude()
        recentes = deque(history.load_pairs(config.HISTORY_SIZE), maxlen=config.HISTORY_SIZE)
    except Exception as e:
        ui_queue.put(("error", f"Falha a iniciar o worker (agente/memória): {e}"))
        state.ready()
        _drain_loop(rec_queue, ui_queue, state, controls, stop_event)
        return

    try:
        controls.speaker = tts.get_tts()
    except Exception as e:
        ui_queue.put(("error", f"Falha a carregar a voz TTS: {e}"))
        controls.speaker = None

    # O Whisper large-v3 é lazy: carregava só na 1ª transcrição (30-60s de silêncio
    # com a UI a dizer "idle"). Carrega já, e o estado diz "a carregar modelos".
    try:
        stt.get_model()
    except Exception as e:
        ui_queue.put(("error", f"Falha a carregar o Whisper: {e}"))
    state.ready()

    while not stop_event.is_set():
        try:
            job = rec_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if job is None:
            break

        kind, payload, cancel = job   # cancel é o Event deste job, criado no enqueue
        speaker = controls.speaker
        resposta = None
        try:
            texto = stt.transcribe_file(payload) if kind == "audio" else payload
            if cancel.is_set():
                raise JobCancelado()
            if texto.strip():
                ui_queue.put(("user", texto))
                history.append("user", texto)
                # Índice lido a cada job, não uma vez no arranque: memórias que o
                # agente escreva durante a sessão entram logo no prompt seguinte.
                index = memory.read_index()

                def on_delta(pedaco, _cancel=cancel):
                    # Depois do Parar, nenhum pedaço novo pode chegar à chat —
                    # senão reabre um bloco delta que já foi fechado pelo "parado.".
                    if not _cancel.is_set():
                        ui_queue.put(("delta", pedaco))

                comp = router.escolher_modelo(texto)
                model_id = router.modelo_id(comp)
                ui_queue.put(("modelo", router.nome_curto(model_id)))
                resposta = asyncio.run(
                    ask_cancelavel(jc, build_prompt(index, recentes, texto), cancel,
                                   on_delta=on_delta, model=model_id)
                )
                if resposta:
                    ui_queue.put(("assistant", resposta))
                    history.append("assistant", resposta)
                    recentes.append((texto, resposta))
                else:
                    # Só tool calls, sem texto final. Persistir "" partia os pares
                    # do histórico (o load filtra text vazio) e poluía o prompt.
                    ui_queue.put(("info", "o agente não devolveu texto"))
        except JobCancelado:
            pass   # o "parado." já foi escrito na chat por quem carregou no botão
        except Exception as e:
            ui_queue.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            # job_done ANTES do unlink: no Windows um handle preso faz o unlink
            # rebentar (PermissionError, que o missing_ok não cobre) — e isso
            # matava a thread com o estado preso em "a processar" para sempre.
            vai_falar = bool(
                resposta and speaker and tts_enabled.is_set() and not cancel.is_set()
            )
            state.job_done(speaking=vai_falar)
            if kind == "audio":
                with contextlib.suppress(OSError):
                    Path(payload).unlink(missing_ok=True)

        # Fora do job: falar não é "a processar". Estado passa a "a falar".
        if vai_falar:
            try:
                speaker.speak(resposta, cancel=cancel)
            except Exception as e:
                ui_queue.put(("error", f"TTS: {type(e).__name__}: {e}"))
            finally:
                state.speaking(False)
        # Só depois da fala: o Parar durante a síntese ainda tem de apanhar este Event.
        controls.job_acabou(cancel)


def main():
    ui_queue: "queue.Queue" = queue.Queue()
    rec_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    tts_enabled = threading.Event()
    tts_enabled.set()
    controls = Controls()
    state = StateBus(ui_queue)

    # Liga a tool `abrir_consola` ao encerramento limpo e ao reinício: quando a
    # consola do Fábio acabar, ela pede "sair" pela mesma via do tray e marca
    # este evento — o main() relança o processo só depois do mainloop terminar.
    reiniciar_event = threading.Event()
    brain_tools.configurar_reinicio(ui_queue, reiniciar_event.set)

    # Resumo da última consola (ou o log, em fallback), se ficou pendente de um
    # reinício anterior — consumido aqui, não repete no próximo arranque.
    resumo_consola = brain_tools.ler_resumo_consola_pendente()
    if resumo_consola:
        ui_queue.put(("info", f"[consola] {resumo_consola}"))

    tecla, tecla_label = hotkey.resolve()   # config.HOTKEY manda; o botão mostra isto
    recorder = hotkey.Recorder(level_cb=lambda rms: ui_queue.put(("level", rms)))

    def begin_recording():
        # try/except porque isto corre no callback do pynput: uma exceção lá
        # (sem mic, device ocupado) mata o listener e a hotkey morre em silêncio.
        try:
            recorder.start()
        except Exception as e:
            ui_queue.put(("error", f"mic: {type(e).__name__}: {e}"))
            return
        state.recording(True)

    def end_recording():
        try:
            path = recorder.stop(new_rec_path())
        except Exception as e:
            path = None
            ui_queue.put(("error", f"mic: {type(e).__name__}: {e}"))
        if path:
            if recorder.esta_mudo():
                # Descarta: silêncio no Whisper não dá vazio, dá alucinação
                # ("Obrigado." e afins) — e isso virava prompt real para o agente.
                ui_queue.put(("info", "mic não captou som — gravação descartada; vê o dispositivo de entrada"))
                with contextlib.suppress(OSError):
                    Path(path).unlink(missing_ok=True)
            else:
                state.job_start()   # conta o job *antes* de baixar recording: nunca pisca "idle"
                rec_queue.put(("audio", path, controls.novo_job()))
        state.recording(False)
        ui_queue.put(("level", 0.0))

    def submit_text(texto: str):
        state.job_start()
        rec_queue.put(("text", texto, controls.novo_job()))   # salta o STT: entra direto na pipeline

    def cancelar():
        # Larga o que está em fila, mata o que está em curso, corta a fala.
        drenados = []
        while True:
            try:
                job = rec_queue.get_nowait()
            except queue.Empty:
                break
            if job is None:
                rec_queue.put(None)   # sentinela de fecho: repõe-na e para de drenar
                break
            drenados.append(job)
        controls.parar()
        for kind, payload, cancel in drenados:
            if kind == "audio":
                with contextlib.suppress(OSError):
                    Path(payload).unlink(missing_ok=True)   # wav de um job que nunca vai correr
            controls.job_acabou(cancel)
            state.job_done()
        ui_queue.put(("info", "parado."))

    global_hotkey = hotkey.GlobalHotkey(tecla, begin_recording, end_recording)
    global_hotkey.start()

    worker = threading.Thread(
        target=worker_loop,
        args=(rec_queue, ui_queue, state, controls, stop_event, tts_enabled),
        daemon=True,
    )
    worker.start()

    def on_close():
        stop_event.set()
        controls.parar()      # não ficar preso num sd.wait() de 90s à espera do fim da fala
        rec_queue.put(None)
        global_hotkey.stop()

    ui_app.launch(
        begin_recording, end_recording, ui_queue, on_close, tts_enabled,
        on_text=submit_text, on_cancel=cancelar, hotkey_label=tecla_label,
        historico=history.load(config.HISTORY_REPLAY),
    )

    # Só depois do mainloop acabar (encerramento limpo já feito): relança a app.
    # Não é os._exit — o processo atual termina sozinho ao cair fora do main().
    if reiniciar_event.is_set():
        subprocess.Popen(
            [sys.executable, str(config.PROJECT_ROOT / "main.py")],
            cwd=str(config.PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )


if __name__ == "__main__":
    main()
