# tests/test_agent.py
import inspect
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

def test_ask_is_async():
    assert inspect.iscoroutinefunction(JeanClaude.ask)
