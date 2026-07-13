# tests/test_tools.py
import asyncio
import threading
import time

import brain.tools as tools
from core import config


def _run(args):
    return asyncio.run(tools.abrir_consola.handler(args))


def _texto_de(resultado) -> str:
    return resultado["content"][0]["text"]


def _preparar_ficheiros(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEDIDO_CONSOLA", tmp_path / "pedido-consola.md")
    monkeypatch.setattr(config, "CONSOLA_ULTIMA", tmp_path / "consola-ultima.md")
    monkeypatch.setattr(config, "CONSOLA_LOG", tmp_path / "consola-log.txt")


class FakeProc:
    """Popen falso: `wait()` só destranca quando o teste manda (`terminar()`)."""

    def __init__(self):
        self._fim = threading.Event()

    def terminar(self):
        self._fim.set()

    def wait(self):
        self._fim.wait(timeout=0.3)


def test_abrir_consola_escreve_pedido_e_lanca_claude_em_modo_automatico(monkeypatch, tmp_path):
    chamadas = []
    _preparar_ficheiros(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda _: "C:/npm/claude.cmd")
    monkeypatch.setattr(tools.sys, "platform", "win32")
    monkeypatch.setattr(
        tools.subprocess, "Popen", lambda *a, **k: (chamadas.append((a, k)), FakeProc())[1]
    )
    tools.configurar_reinicio(None, None)   # sem app real ligada, a thread não deve rebentar

    pedido = "muda a cor do botão Parar para azul & apaga tudo"
    res = _run({"pedido": pedido})

    assert "is_error" not in res
    # pedido foi para o ficheiro, inteiro
    assert pedido in config.PEDIDO_CONSOLA.read_text(encoding="utf-8")
    # consola lançada com o prompt FIXO; o texto do Fábio NUNCA entra no comando
    # (um `&` no pedido dentro de `cmd /c` seria injeção de shell)
    (args, kwargs), = chamadas
    cmd = args[0]
    assert cmd[:2] == ["cmd", "/c"]
    assert cmd[2] == "claude"
    # flag de modo automático presente no comando (confirmada em `claude --help`)
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[-1] == tools._PROMPT_CONSOLA
    assert all(pedido not in parte for parte in cmd)
    assert kwargs["cwd"] == str(config.PROJECT_ROOT)
    # stdout/stderr capturados em ficheiro, não deixados a apontar para a consola
    assert kwargs["stdout"] is not None
    assert kwargs["stderr"] == tools.subprocess.STDOUT


def test_abrir_consola_larga_config_isolada_mas_respeita_a_do_fabio(monkeypatch, tmp_path):
    """A consola tem de abrir com a config global (plugins/skills do Fábio).
    CLAUDE_CONFIG_DIR a apontar para a nossa .jc-config é contaminação e sai;
    apontar para outro sítio é escolha do Fábio e fica."""
    chamadas = []
    _preparar_ficheiros(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(tools.sys, "platform", "win32")
    monkeypatch.setattr(tools.subprocess, "Popen", lambda *a, **k: (chamadas.append(k), FakeProc())[1])
    tools.configurar_reinicio(None, None)

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config.CONFIG_DIR))
    _run({"pedido": "muda x"})
    assert "CLAUDE_CONFIG_DIR" not in chamadas[0]["env"]

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "D:/config-do-fabio")
    _run({"pedido": "muda x"})
    assert chamadas[1]["env"]["CLAUDE_CONFIG_DIR"] == "D:/config-do-fabio"


def test_abrir_consola_sem_pedido_e_erro(monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "win32")
    res = _run({"pedido": "   "})
    assert res.get("is_error") is True


def test_abrir_consola_sem_claude_no_path_explica(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.sys, "platform", "win32")
    monkeypatch.setattr(tools.shutil, "which", lambda _: None)
    res = _run({"pedido": "qualquer coisa"})
    assert res.get("is_error") is True
    assert "PATH" in _texto_de(res)


def test_abrir_consola_popen_falhado_nao_rebenta(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.sys, "platform", "win32")
    monkeypatch.setattr(tools.shutil, "which", lambda _: "claude")

    def rebenta(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(tools.subprocess, "Popen", rebenta)
    res = _run({"pedido": "qualquer coisa"})
    assert res.get("is_error") is True
    assert "boom" in _texto_de(res)


def test_reinicio_so_dispara_depois_do_proc_wait_acabar(monkeypatch, tmp_path):
    """A thread que espera a consola não pode marcar reinício nem pedir 'sair'
    enquanto o processo continua vivo — só depois de `proc.wait()` retornar."""
    _preparar_ficheiros(monkeypatch, tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(tools.sys, "platform", "win32")

    fake_proc = FakeProc()
    monkeypatch.setattr(tools.subprocess, "Popen", lambda *a, **k: fake_proc)

    marcado = threading.Event()
    ui_queue = []

    class FilaFalsa:
        def put(self, item):
            ui_queue.append(item)

    tools.configurar_reinicio(FilaFalsa(), marcado.set)

    _run({"pedido": "qualquer coisa"})

    # a consola "ainda não acabou": nem o evento nem a fila foram tocados
    time.sleep(0.1)
    assert not marcado.is_set()
    assert ui_queue == []

    # agora a consola "acaba" -> proc.wait() destranca -> a thread reage
    fake_proc.terminar()
    assert marcado.wait(timeout=2)
    for _ in range(50):
        if ui_queue:
            break
        time.sleep(0.05)
    assert ui_queue == [("tray", "sair")]


def test_resumo_consola_le_e_apaga_o_ficheiro(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    config.CONSOLA_ULTIMA.write_text("mudei o botão, testes passaram", encoding="utf-8")

    resumo = tools.ler_resumo_consola_pendente()

    assert resumo == "mudei o botão, testes passaram"
    assert not config.CONSOLA_ULTIMA.exists()
    # não repete: chamada seguinte não encontra nada
    assert tools.ler_resumo_consola_pendente() is None


def test_resumo_consola_cai_para_o_log_se_nao_ha_resumo(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    config.CONSOLA_LOG.write_text("saida bruta do processo", encoding="utf-8")

    resumo = tools.ler_resumo_consola_pendente()

    assert resumo == "saida bruta do processo"
    assert not config.CONSOLA_LOG.exists()


def test_resumo_consola_none_se_nao_ha_nada_pendente(monkeypatch, tmp_path):
    _preparar_ficheiros(monkeypatch, tmp_path)
    assert tools.ler_resumo_consola_pendente() is None
