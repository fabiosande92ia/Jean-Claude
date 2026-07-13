# tests/test_agent.py
import asyncio
import inspect
import os
from claude_agent_sdk import AssistantMessage, StreamEvent, TextBlock
import brain.agent as agent_mod
from brain.agent import JeanClaude
from core import config

def test_options_are_isolated_and_basic():
    jc = JeanClaude()
    opts = jc.build_options()
    # isolamento: não carrega settings do utilizador
    assert opts.setting_sources == []
    # persona vem do CLAUDE.md
    system = opts.system_prompt if isinstance(opts.system_prompt, str) else str(opts.system_prompt)
    assert "Jean Claude" in system
    # só tools básicas
    assert set(opts.allowed_tools) >= set(config.ALLOWED_TOOLS)
    assert "MCP" not in " ".join(opts.allowed_tools)
    # tools próprias (screenshot, abrir_consola) registadas e permitidas
    from brain.tools import SCREENSHOT_TOOL_NAME, CONSOLE_TOOL_NAME, JC_TOOL_NAMES
    assert SCREENSHOT_TOOL_NAME in opts.allowed_tools
    assert CONSOLE_TOOL_NAME in opts.allowed_tools
    assert set(JC_TOOL_NAMES) <= set(opts.allowed_tools)

def test_caveman_vem_do_plugin_em_ultra():
    """Estilo do JC = plugin caveman real, nível ultra fixo via env do subprocess."""
    opts = JeanClaude().build_options()
    assert opts.env.get("CAVEMAN_DEFAULT_MODE") == "ultra"
    plugin = config.caveman_plugin_path()
    if plugin is None:  # máquina sem o plugin instalado: JC fala normal, sem plugins
        assert opts.plugins == []
    else:
        assert {"type": "local", "path": str(plugin)} in opts.plugins
        assert (plugin / ".claude-plugin" / "plugin.json").is_file()

def test_config_isolada_vai_no_env_das_options_nao_no_processo():
    """Mutar os.environ contaminava tudo o que a app lançasse depois: a consola
    do abrir_consola herdava a .jc-config e abria sem os plugins do Fábio."""
    antes = os.environ.get("CLAUDE_CONFIG_DIR")
    opts = JeanClaude().build_options()
    assert opts.env.get("CLAUDE_CONFIG_DIR") == str(config.CONFIG_DIR)
    assert os.environ.get("CLAUDE_CONFIG_DIR") == antes   # processo intacto

def test_ask_is_async():
    assert inspect.iscoroutinefunction(JeanClaude.ask)


def test_include_partial_messages_ligado():
    """Sem isto o SDK nunca emite StreamEvent — os deltas ficam mudos."""
    assert JeanClaude().build_options().include_partial_messages is True


def test_build_options_passa_o_modelo():
    jc = JeanClaude()
    opts = jc.build_options(model="claude-opus-4-8")
    assert opts.model == "claude-opus-4-8"


def test_build_options_sem_modelo_fica_none():
    jc = JeanClaude()
    opts = jc.build_options()
    assert opts.model is None


class _FakeSDKClient:
    """Cliente SDK de mentira: dá as mensagens à mão, sem subprocess nenhum."""

    def __init__(self, mensagens):
        self._mensagens = mensagens
        self.prompt_recebido = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def query(self, prompt):
        self.prompt_recebido = prompt

    async def receive_response(self):
        for msg in self._mensagens:
            yield msg


def _delta_evento(texto, tipo="text_delta"):
    return StreamEvent(
        uuid="u", session_id="s",
        event={"type": "content_block_delta", "delta": {"type": tipo, "text": texto}},
    )


def test_ask_entrega_deltas_por_ordem_e_devolve_o_texto_final(monkeypatch):
    mensagens = [
        _delta_evento("ola "),
        _delta_evento("mundo"),
        AssistantMessage(content=[TextBlock(text="ola mundo")], model="m"),
    ]
    monkeypatch.setattr(agent_mod, "ClaudeSDKClient", lambda options=None: _FakeSDKClient(mensagens))
    recebidos = []
    resposta = asyncio.run(JeanClaude().ask("oi", on_delta=recebidos.append))
    assert recebidos == ["ola ", "mundo"]
    assert resposta == "ola mundo"
    assert resposta == "".join(recebidos)   # texto final == soma dos deltas


def test_ask_ignora_eventos_que_nao_sao_texto(monkeypatch):
    mensagens = [
        _delta_evento("{}", tipo="input_json_delta"),   # pedaço de tool_use, não texto
        AssistantMessage(content=[TextBlock(text="resultado")], model="m"),
    ]
    monkeypatch.setattr(agent_mod, "ClaudeSDKClient", lambda options=None: _FakeSDKClient(mensagens))
    recebidos = []
    resposta = asyncio.run(JeanClaude().ask("oi", on_delta=recebidos.append))
    assert recebidos == []
    assert resposta == "resultado"


def test_ask_sem_on_delta_nao_rebenta(monkeypatch):
    mensagens = [_delta_evento("x"), AssistantMessage(content=[TextBlock(text="x")], model="m")]
    monkeypatch.setattr(agent_mod, "ClaudeSDKClient", lambda options=None: _FakeSDKClient(mensagens))
    assert asyncio.run(JeanClaude().ask("oi")) == "x"


def test_ask_so_tool_calls_sem_texto_devolve_vazio(monkeypatch):
    """Contrato antigo mantido: sem TextBlock final, devolve "" (main.py manda 'info')."""
    mensagens = [AssistantMessage(content=[], model="m")]
    monkeypatch.setattr(agent_mod, "ClaudeSDKClient", lambda options=None: _FakeSDKClient(mensagens))
    assert asyncio.run(JeanClaude().ask("oi")) == ""
