import pytest
from ui import mascot


def test_solta_curto_e_clique():
    assert mascot.foi_clique(0, 0)
    assert mascot.foi_clique(3, -2)


def test_solta_longo_e_arrasto():
    assert not mascot.foi_clique(10, 0)
    assert not mascot.foi_clique(0, 30)


def test_balao_curto_fica_igual():
    assert mascot.truncar_balao("ok feito") == "ok feito"


def test_balao_longo_corta_com_reticencias():
    texto = "x" * 300
    out = mascot.truncar_balao(texto)
    assert len(out) <= mascot.MAX_BALAO + 1
    assert out.endswith("…")


def test_balao_colapsa_espacos_e_newlines():
    assert mascot.truncar_balao("linha1\n\n  linha2") == "linha1 linha2"


def test_pos_guarda_sem_apagar_outras_chaves(tmp_path, monkeypatch):
    from ui import app as ui_app
    f = tmp_path / "ui.json"
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", f)
    ui_app.guardar_ui_state({"geometry": "540x680+10+10"})
    mascot.guardar_pos("+200+300")
    assert mascot.carregar_pos() == "+200+300"
    assert ui_app.carregar_ui_state()["geometry"] == "540x680+10+10"


def test_pos_ausente_e_none(tmp_path, monkeypatch):
    from ui import app as ui_app
    monkeypatch.setattr(ui_app.config, "UI_STATE_FILE", tmp_path / "nada.json")
    assert mascot.carregar_pos() is None
