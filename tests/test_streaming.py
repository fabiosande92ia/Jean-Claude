# tests/test_streaming.py — deltas do worker_loop até à ui_queue
import queue
import threading

import main as main_mod


def _monta_worker(monkeypatch, fake_jc):
    monkeypatch.setattr(main_mod, "JeanClaude", lambda: fake_jc)
    monkeypatch.setattr(main_mod.history, "load_pairs", lambda n: [])
    monkeypatch.setattr(main_mod.history, "append", lambda *a, **k: None)
    monkeypatch.setattr(main_mod.memory, "read_index", lambda: "")
    monkeypatch.setattr(
        main_mod.tts, "get_tts",
        lambda: (_ for _ in ()).throw(RuntimeError("sem voz no teste")),
    )
    monkeypatch.setattr(main_mod.stt, "get_model", lambda: None)


def _so_delta_e_final(eventos):
    return [(k, v) for k, v in eventos if k in ("delta", "assistant")]


def test_worker_loop_entrega_deltas_por_ordem_sem_duplicar(monkeypatch):
    pedacos = ["ola ", "mundo"]
    texto_final = "ola mundo"

    class FakeJC:
        async def ask(self, prompt, on_delta=None):
            for p in pedacos:
                if on_delta:
                    on_delta(p)
            return texto_final

    _monta_worker(monkeypatch, FakeJC())

    rec_queue: "queue.Queue" = queue.Queue()
    ui_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    tts_enabled = threading.Event()
    controls = main_mod.Controls()
    state = main_mod.StateBus(ui_queue)

    rec_queue.put(("text", "oi", controls.novo_job()))
    rec_queue.put(None)   # fecha o worker depois deste job

    main_mod.worker_loop(rec_queue, ui_queue, state, controls, stop_event, tts_enabled)

    eventos = []
    while not ui_queue.empty():
        eventos.append(ui_queue.get_nowait())

    relevantes = _so_delta_e_final(eventos)
    assert relevantes == [("delta", "ola "), ("delta", "mundo"), ("assistant", "ola mundo")]
    # texto final == concatenação dos deltas (contrato do ponto 2 do pedido)
    assert relevantes[-1][1] == "".join(p for k, p in relevantes if k == "delta")


def test_worker_loop_para_de_emitir_deltas_apos_cancelar_a_meio(monkeypatch):
    """Depois do Parar, nenhum pedaço novo pode chegar — senão reabre um bloco
    delta já fechado pelo 'parado.' na UI."""

    class FakeJC:
        async def ask(self, prompt, on_delta=None):
            if on_delta:
                on_delta("primeiro ")
            cancel_evento.set()   # simula o Fábio a carregar em Parar a meio da resposta
            if on_delta:
                on_delta("nunca deve chegar à ui_queue")
            return "resposta parcial"

    _monta_worker(monkeypatch, FakeJC())

    rec_queue: "queue.Queue" = queue.Queue()
    ui_queue: "queue.Queue" = queue.Queue()
    stop_event = threading.Event()
    tts_enabled = threading.Event()
    controls = main_mod.Controls()
    state = main_mod.StateBus(ui_queue)

    cancel_evento = controls.novo_job()
    rec_queue.put(("text", "oi", cancel_evento))
    rec_queue.put(None)

    main_mod.worker_loop(rec_queue, ui_queue, state, controls, stop_event, tts_enabled)

    eventos = []
    while not ui_queue.empty():
        eventos.append(ui_queue.get_nowait())

    relevantes = _so_delta_e_final(eventos)
    assert ("delta", "nunca deve chegar à ui_queue") not in relevantes
    assert relevantes[0] == ("delta", "primeiro ")
