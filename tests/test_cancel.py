import asyncio
import threading
import pytest
from main import Controls, ask_cancelavel, JobCancelado


class FakeJC:
    """Agente falso: demora `delay` a responder e regista se foi mesmo cancelado."""

    def __init__(self, delay: float):
        self.delay = delay
        self.cancelada = False

    async def ask(self, prompt: str, on_delta=None, model=None) -> str:
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelada = True
            raise
        return f"resposta a {prompt}"


def test_sem_cancel_devolve_a_resposta():
    jc = FakeJC(delay=0.01)
    assert asyncio.run(ask_cancelavel(jc, "olá", threading.Event())) == "resposta a olá"


def test_cancel_a_meio_mata_o_pedido():
    """O bug: asyncio.run(jc.ask(...)) era monolítico — havia que esperar pelo agente todo."""
    jc = FakeJC(delay=30)
    cancel = threading.Event()

    async def corre():
        asyncio.get_running_loop().call_later(0.05, cancel.set)
        return await ask_cancelavel(jc, "esquece", cancel)

    with pytest.raises(JobCancelado):
        asyncio.run(corre())
    assert jc.cancelada   # a task foi cancelada de facto, não abandonada a correr


def test_cancel_ja_ligado_nem_chega_a_esperar():
    jc = FakeJC(delay=30)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(JobCancelado):
        asyncio.run(ask_cancelavel(jc, "olá", cancel))


def test_parar_mata_todos_os_jobs_vivos():
    c = Controls()
    a, b = c.novo_job(), c.novo_job()
    c.parar()
    assert a.is_set() and b.is_set()


def test_job_novo_depois_do_parar_nasce_limpo():
    """O bug do Event único partilhado: o clear() no início do job apagava um
    Parar em trânsito, e o job que devia morrer corria todo."""
    c = Controls()
    velho = c.novo_job()
    c.parar()
    novo = c.novo_job()
    assert velho.is_set()
    assert not novo.is_set()


def test_job_acabado_ja_nao_e_alvo_do_parar():
    c = Controls()
    ev = c.novo_job()
    c.job_acabou(ev)
    c.parar()
    assert not ev.is_set()
    c.job_acabou(ev)   # remover duas vezes não rebenta
