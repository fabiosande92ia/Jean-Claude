from core import config

def test_claude_md_exists_and_has_persona():
    text = config.CLAUDE_MD.read_text(encoding="utf-8")
    low = text.lower()
    assert "jean claude" in low
    assert "fábio" in low or "fabio" in low
    assert "caveman" in low
    # nunca se identifica como Claude/Anthropic
    assert "nunca" in low and "anthropic" in low
