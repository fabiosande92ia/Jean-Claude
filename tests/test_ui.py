from ui import app as ui_app


def test_state_maps_cover_all_states():
    expected = {"idle", "recording", "processing"}
    assert set(ui_app.STATE_COLORS) == expected
    assert set(ui_app.STATE_LABELS) == expected


def test_launch_is_callable():
    assert callable(ui_app.launch)
