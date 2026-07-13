# tests/test_memory.py
from pathlib import Path
import brain.memory as memory
from core import config

def test_write_and_index(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path)
    (tmp_path / "MEMORY.md").write_text("# Índice\n", encoding="utf-8")

    p = memory.write_memory("pc-gpu", "GPU do Fabio", "RTX 3060, 12GB VRAM.", "pc")
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "RTX 3060" in content
    assert "type: pc" in content

    index = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "pc-gpu.md" in index
    assert "GPU do Fabio" in index
