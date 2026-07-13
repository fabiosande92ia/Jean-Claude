import inspect
import pytest
from ui import app as ui_app

EXPECTED = {"idle", "loading", "recording", "processing", "speaking"}


def test_state_maps_cover_all_states():
    assert set(ui_app.STATE_COLORS) == EXPECTED
    assert set(ui_app.STATE_LABELS) == EXPECTED


def test_estado_desconhecido_nao_rebenta():
    """Antes era STATE_LABELS[payload]: um KeyError matava o _poll e a UI congelava."""
    assert ui_app.STATE_LABELS.get("xpto", "xpto") == "xpto"
    assert ui_app.STATE_COLORS.get("xpto", ui_app.UNKNOWN_COLOR) == ui_app.UNKNOWN_COLOR


def test_estados_ocupados_sao_estados_reais():
    """O spinner/elapsed só pode acender em estados que existem."""
    assert set(ui_app.ESTADOS_OCUPADOS) <= EXPECTED
    assert "idle" not in ui_app.ESTADOS_OCUPADOS


def test_launch_aceita_texto_cancelar_e_historico():
    params = inspect.signature(ui_app.launch).parameters
    for p in ("on_text", "on_cancel", "hotkey_label", "historico"):
        assert p in params


def test_hora_formata_iso_e_cai_para_agora():
    assert ui_app._hora("2026-07-13T09:05:00") == "09:05"
    assert len(ui_app._hora(None)) == 5      # HH:MM de agora
    assert len(ui_app._hora("lixo")) == 5    # ts corrompido não rebenta a chat


@pytest.mark.parametrize("rms", [0.0, 0.001, 0.05, 1.0, 99.0, -1.0])
def test_nivel_do_vu_fica_sempre_entre_0_e_1(rms):
    assert 0.0 <= ui_app.nivel_vu(rms) <= 1.0


def test_vu_sobe_com_o_sinal():
    silencio = ui_app.nivel_vu(0.0)
    fala = ui_app.nivel_vu(0.05)
    assert silencio == 0.0
    assert 0.15 < fala < 1.0        # fala normal: barra visível, não colada ao zero
    assert ui_app.nivel_vu(1.0) == 1.0   # clip satura, não estoura o canvas
