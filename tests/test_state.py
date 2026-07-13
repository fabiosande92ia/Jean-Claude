import queue
from main import StateBus


def drain(q):
    out = []
    while not q.empty():
        kind, payload = q.get()
        if kind == "state":
            out.append(payload)
    return out


def test_arranque_diz_a_carregar():
    q = queue.Queue()
    StateBus(q)
    assert drain(q) == ["loading"]


def test_so_fica_idle_depois_de_pronto():
    q = queue.Queue()
    bus = StateBus(q)
    drain(q)
    bus.ready()
    assert drain(q) == ["idle"]


def test_job_atrasado_nao_pisca_idle_sobre_gravacao_nova():
    """O bug: o `idle` do job antigo chegava depois do `recording` do job novo."""
    q = queue.Queue()
    bus = StateBus(q)
    bus.ready()
    drain(q)

    bus.recording(True)          # 1ª gravação
    bus.job_start()
    bus.recording(False)         # -> processing
    bus.recording(True)          # 2ª gravação, enquanto a 1ª ainda processa
    bus.job_done()               # 1º job acaba: NÃO pode dizer idle, o mic está aberto
    assert drain(q) == ["recording", "processing", "recording"]

    bus.job_start()
    bus.recording(False)
    bus.job_done()
    assert drain(q) == ["processing", "idle"]


def test_falar_nao_e_processar():
    q = queue.Queue()
    bus = StateBus(q)
    bus.ready()
    drain(q)
    bus.job_start()
    bus.job_done(speaking=True)   # atómico: sem "idle" a piscar entre processar e falar
    bus.speaking(False)
    assert drain(q) == ["processing", "speaking", "idle"]


def test_nao_repete_o_mesmo_estado():
    q = queue.Queue()
    bus = StateBus(q)
    bus.ready()
    drain(q)
    bus.recording(True)
    bus.recording(True)
    assert drain(q) == ["recording"]


def test_job_done_a_mais_nao_poe_pendentes_negativos():
    q = queue.Queue()
    bus = StateBus(q)
    bus.ready()
    drain(q)
    bus.job_done()
    bus.job_start()
    assert drain(q) == ["processing"]
