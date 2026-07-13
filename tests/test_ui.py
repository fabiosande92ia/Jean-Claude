from ui import app as ui_app

EXPECTED = {"idle", "loading", "recording", "processing", "speaking"}


def test_state_maps_cover_all_states():
    assert set(ui_app.STATE_COLORS) == EXPECTED
    assert set(ui_app.STATE_LABELS) == EXPECTED


def test_estado_desconhecido_nao_rebenta():
    """Antes era STATE_LABELS[payload]: um KeyError matava o _poll e a UI congelava."""
    assert ui_app.STATE_LABELS.get("xpto", "xpto") == "xpto"
    assert ui_app.STATE_COLORS.get("xpto", ui_app.UNKNOWN_COLOR) == ui_app.UNKNOWN_COLOR


def test_launch_is_callable():
    assert callable(ui_app.launch)
