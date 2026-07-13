# tests/test_config.py
from pathlib import Path
from core import config

def test_paths_exist_and_are_absolute():
    assert config.PROJECT_ROOT.is_absolute()
    assert config.CONFIG_DIR.name == ".jc-config"
    assert config.MEMORY_DIR.name == "memory"
    assert config.CLAUDE_MD == config.CONFIG_DIR / "CLAUDE.md"

def test_allowed_tools_are_basic_only():
    expected = {"Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"}
    assert set(config.ALLOWED_TOOLS) == expected

def test_defaults():
    assert config.WHISPER_MODEL == "large-v3"
    assert config.HOTKEY == "ctrl+space"
