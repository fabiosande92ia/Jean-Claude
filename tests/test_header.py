from ui.app import compor_header


def test_header_sem_modelo():
    assert compor_header("idle", None) == "idle"


def test_header_com_modelo():
    assert compor_header("a processar", "opus") == "a processar · opus"
