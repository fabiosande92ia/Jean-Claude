import brain.consola as consola


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
