import pytest
from ui import mascot, sprites


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


# --- máquina de frames (sem abrir janelas) -----------------------------------
def _mascot_sem_janela(estado="idle"):
    """Mascot sem __init__: só os atributos que a lógica de frames usa. O mesmo
    padrão do app_falso em test_ui.py — testa-se a lógica, não o desenho."""
    m = object.__new__(mascot.Mascot)
    m._estado = estado
    m._frame_idx = 0
    m._extra = None
    return m


def test_estado_desconhecido_cai_em_idle():
    m = _mascot_sem_janela("speaking")
    mascot.Mascot.set_state(m, "xpto")
    assert m._estado == "idle"


def test_mudar_de_estado_reinicia_o_frame():
    m = _mascot_sem_janela("idle")
    m._frame_idx = 3
    mascot.Mascot.set_state(m, "recording")
    assert m._estado == "recording"
    assert m._frame_idx == 0


def test_mesmo_estado_nao_reinicia_o_frame():
    """State chega repetido do _poll; reiniciar a cada emissão congelava a
    animação no frame 0."""
    m = _mascot_sem_janela("idle")
    m._frame_idx = 3
    mascot.Mascot.set_state(m, "idle")
    assert m._frame_idx == 3


def test_proximo_frame_avanca_e_da_a_volta():
    m = _mascot_sem_janela("recording")
    n = len(sprites.FRAMES["recording"])
    assert n == 2
    frames = [m._proximo_frame() for _ in range(n + 1)]
    assert all(f is not None for f in frames)
    assert frames[0] == frames[2]       # deu a volta
    assert m._frame_idx == 1


def test_extra_tem_prioridade_sobre_o_estado():
    m = _mascot_sem_janela("idle")
    m._extra = sprites.EXTRAS["dormir"]
    assert m._frames_atuais() is sprites.EXTRAS["dormir"]
