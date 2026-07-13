import json
import threading
import brain.consola as consola
import brain.tools  # noqa: F401 — pré-carrega ANTES do monkeypatch de subprocess.Popen: o
# import tardio dentro da thread (`from brain.tools import ...`) reexecutaria a cadeia
# claude_agent_sdk -> mcp, que num import a frio avalia `subprocess.Popen[bytes]` (anotação de
# tipo em mcp/os/win32/utilities.py) — com o Popen já trocado por uma lambda nos testes, isso
# rebenta com TypeError. Pré-importar põe o módulo em sys.modules com o Popen real ainda vivo.
from core import config


class FakeProc:
    """Popen falso: stdout entrega linhas pré-definidas; wait() destranca quando o teste manda."""
    def __init__(self, linhas):
        self.stdout = iter(linhas)
        self._fim = threading.Event()

    def wait(self):
        self._fim.wait(timeout=1.0)
        self._fim.set()

    def terminar(self):
        self._fim.set()


class FilaFalsa:
    def __init__(self):
        self.itens = []
    def put(self, item):
        self.itens.append(item)


def _preparar(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEDIDO_CONSOLA", tmp_path / "pedido-consola.md")
    monkeypatch.setattr(config, "CONSOLA_ULTIMA", tmp_path / "consola-ultima.md")
    monkeypatch.setattr(config, "CONSOLA_LOG", tmp_path / "consola-log.txt")
    monkeypatch.setattr(consola.sys, "platform", "win32")
    monkeypatch.setattr(consola.shutil, "which", lambda _: "claude")


def test_start_escreve_pedido_e_lanca_com_modelo(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    chamadas = []
    linhas = [json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "oi"}]}}) + "\n",
              json.dumps({"type": "result", "subtype": "success"}) + "\n"]
    proc = FakeProc(linhas)
    monkeypatch.setattr(consola.subprocess, "Popen", lambda *a, **k: (chamadas.append((a, k)), proc)[1])
    config.CONSOLA_ULTIMA.write_text("mudei X, testes ok", encoding="utf-8")

    fila = FilaFalsa()
    terminou = threading.Event()
    runner = consola.ConsoleRunner(fila, on_terminou=terminou.set)

    ok, motivo = runner.start("muda a cor do botão", "alta")
    assert ok and motivo == ""
    assert "muda a cor do botão" in config.PEDIDO_CONSOLA.read_text(encoding="utf-8")

    (args, kwargs), = chamadas
    cmd = args[0]
    assert "--model" in cmd and "claude-opus-4-8" in cmd          # complexidade "alta"
    assert "--dangerously-skip-permissions" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert kwargs["creationflags"] == consola.subprocess.CREATE_NO_WINDOW
    assert kwargs["stdout"] == consola.subprocess.PIPE
    assert kwargs["stdin"] == consola.subprocess.DEVNULL
    assert all("muda a cor" not in str(p) for p in cmd)           # pedido nunca no comando

    proc.terminar()
    assert terminou.wait(timeout=2)
    kinds = [m[0] for m in fila.itens]
    assert kinds[0] == "consola_estado" and fila.itens[0][1]["run"] is True
    assert fila.itens[0][1]["modelo"] == "opus"
    assert ("consola", "oi") in fila.itens
    assert ("consola_fim", "mudei X, testes ok") in fila.itens
    assert not runner.is_running()


def test_start_recusa_segunda_consola(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    proc = FakeProc([])                       # stdout vazio: reader fica logo no wait()
    monkeypatch.setattr(consola.subprocess, "Popen", lambda *a, **k: proc)
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)

    ok1, _ = runner.start("pedido 1", "baixa")
    assert ok1 and runner.is_running()
    ok2, motivo = runner.start("pedido 2", "baixa")
    assert ok2 is False and "a correr" in motivo
    proc.terminar()


def test_start_fora_de_windows_recusa(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(consola.sys, "platform", "linux")
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)
    ok, motivo = runner.start("x", "media")
    assert ok is False and "Windows" in motivo


def test_start_sem_claude_no_path_recusa(monkeypatch, tmp_path):
    _preparar(monkeypatch, tmp_path)
    monkeypatch.setattr(consola.shutil, "which", lambda _: None)
    runner = consola.ConsoleRunner(FilaFalsa(), on_terminou=lambda: None)
    ok, motivo = runner.start("x", "media")
    assert ok is False and "PATH" in motivo


def test_parse_texto_do_assistant():
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": "olá"}]}}
    assert consola.parse_evento(ev) == "olá"


def test_parse_tool_use_mostra_ferramenta_e_alvo():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "brain/agent.py"}},
    ]}}
    assert consola.parse_evento(ev) == "🔧 Edit: brain/agent.py"


def test_parse_tool_use_bash_usa_command():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}},
    ]}}
    assert consola.parse_evento(ev) == "🔧 Bash: pytest"


def test_parse_junta_texto_e_tools():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "vou editar"},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "main.py"}},
    ]}}
    assert consola.parse_evento(ev) == "vou editar\n🔧 Edit: main.py"


def test_parse_result_e_linha_de_fecho():
    assert consola.parse_evento({"type": "result", "subtype": "success"}) == "— consola terminou —"


def test_parse_ignora_system_e_tool_result():
    assert consola.parse_evento({"type": "system", "subtype": "init"}) is None
    assert consola.parse_evento({"type": "user", "message": {"content": []}}) is None


def test_parse_assistant_vazio_e_none():
    ev = {"type": "assistant", "message": {"content": [{"type": "text", "text": "  "}]}}
    assert consola.parse_evento(ev) is None
