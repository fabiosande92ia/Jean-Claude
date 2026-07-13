import pytest
from ui import sprites

ESTADOS = {"idle", "loading", "recording", "processing", "speaking"}


def test_frames_cobrem_todos_os_estados():
    assert set(sprites.FRAMES) == ESTADOS


def test_cada_estado_tem_pelo_menos_um_frame():
    for estado, frames in sprites.FRAMES.items():
        assert len(frames) >= 1, estado


def test_todos_os_frames_validam():
    todos = [f for fs in sprites.FRAMES.values() for f in fs]
    todos += [f for fs in sprites.EXTRAS.values() for f in fs]
    for frame in todos:
        sprites.validar(frame)   # não levanta


def test_frame_com_dimensao_errada_e_recusado():
    curto = ["." * sprites.LARGURA] * (sprites.ALTURA - 1)
    with pytest.raises(ValueError):
        sprites.validar(curto)

    estreito = ["." * (sprites.LARGURA - 1)] * sprites.ALTURA
    with pytest.raises(ValueError):
        sprites.validar(estreito)


def test_frame_com_caracter_desconhecido_e_recusado():
    linhas = ["." * sprites.LARGURA] * sprites.ALTURA
    linhas[0] = "?" + "." * (sprites.LARGURA - 1)
    with pytest.raises(ValueError):
        sprites.validar(linhas)


def test_nenhuma_cor_e_a_cor_chave():
    """A cor-chave é o buraco da transparência: um pixel dela na mascote seria
    um furo por onde se via o desktop."""
    for fs in sprites.FRAMES.values():
        for frame in fs:
            assert sprites.COR_CHAVE not in sprites.cores_do_frame(frame)


def test_extras_tem_as_animacoes_raras():
    assert {"olhar", "dormir", "salto"} <= set(sprites.EXTRAS)
