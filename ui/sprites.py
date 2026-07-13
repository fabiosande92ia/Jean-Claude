# ui/sprites.py
"""
Sprites da mascote como grelhas de texto — sem PNGs, editável e testável.

Cada frame é uma list[str] de ALTURA linhas, cada uma com LARGURA carateres.
Um carácter = uma célula. '.' é transparente. O resto mapeia para PALETA.
A cor-chave da transparência (COR_CHAVE) nunca pode aparecer num frame: seria
um furo por onde se via o desktop através da mascote.
"""

COR_CHAVE = "#ff00fe"
LARGURA = 16
ALTURA = 16

PALETA = {
    ".": None,          # transparente
    "L": "#D97757",     # corpo
    "s": "#bd5f3c",     # sombra do corpo (base)
    "p": "#A6552F",     # pés e braços
    "A": "#A6552F",     # haste da antena
    "T": "#e35d4f",     # ponta da antena
    "V": "#1c2b33",     # visor
    "E": "#59e3d8",     # olhos
    "M": "#3a5560",     # boca (visor um tom acima)
    "B": "#59e3d8",     # barra de loading (mesma cor dos olhos)
}


def cores_do_frame(frame):
    cores = set()
    for linha in frame:
        for ch in linha:
            cor = PALETA.get(ch)
            if cor is not None:
                cores.add(cor)
    return cores


def validar(frame):
    if len(frame) != ALTURA:
        raise ValueError(f"frame tem {len(frame)} linhas, esperado {ALTURA}")
    for i, linha in enumerate(frame):
        if len(linha) != LARGURA:
            raise ValueError(f"linha {i} tem {len(linha)} colunas, esperado {LARGURA}")
        for ch in linha:
            if ch not in PALETA:
                raise ValueError(f"carácter desconhecido {ch!r} na linha {i}")
    if COR_CHAVE in cores_do_frame(frame):
        raise ValueError("frame usa a cor-chave da transparência")


# --- construção dos frames ---------------------------------------------------
# Silhueta base: antena, corpo blob, visor com olhos, braços, pés. As variações
# por estado tocam só a linha dos olhos (6), a da boca (7) e a antena (0).
_BASE = [
    "......T.........",
    "......A.........",
    "....LLLLLLLL....",
    "...LLLLLLLLLL...",
    "..LLLLLLLLLLLL..",
    "..LVVVVVVVVVVL..",
    "..LVVEVVVVEVVL..",
    "..LVVVVVVVVVVL..",
    "..LLLLLLLLLLLL..",
    "..LLLLLLLLLLLL..",
    ".pLLLLLLLLLLLLp.",
    "..LLLLLLLLLLLL..",
    "..sLLLLLLLLLLs..",
    "...ssssssssss...",
    "...pp.....pp....",
    "................",
]

OLHOS_ABERTOS = "..LVVEVVVVEVVL.."
OLHOS_FECHADOS = "..LVVVVVVVVVVL.."
OLHOS_ESQ = "..LVEVVVVEVVVL.."
OLHOS_DIR = "..LVVVEVVVVEVL.."
BOCA_ABERTA = "..LVVVMMMMVVVL.."
BARRA_ESQ = "..LBBBVVVVVVVL.."
BARRA_MEIO = "..LVVVBBBBVVVL.."
BARRA_DIR = "..LVVVVVVVBBBL.."


def _com(olhos=None, boca=None, antena=True, desce=0):
    """Frame a partir da base: linha dos olhos, linha da boca, antena on/off e
    deslocamento vertical (respiração/agachar). desce>0 só é válido porque a
    última linha da base é vazia — o corpo desliza sem perder pixels."""
    f = list(_BASE)
    if olhos:
        f[6] = olhos
    if boca:
        f[7] = boca
    if not antena:
        f[0] = "." * LARGURA
    for _ in range(desce):
        f = ["." * LARGURA] + f[:-1]
    return f


FRAMES = {
    # respira (corpo desce 1 célula) e pestaneja de vez em quando
    "idle": [
        _com(), _com(), _com(),
        _com(desce=1), _com(desce=1),
        _com(), _com(olhos=OLHOS_FECHADOS),
    ],
    # barra a varrer o visor
    "loading": [
        _com(olhos=BARRA_ESQ),
        _com(olhos=BARRA_MEIO),
        _com(olhos=BARRA_DIR),
    ],
    # ponta da antena pisca, olhos fixos
    "recording": [
        _com(),
        _com(antena=False),
    ],
    # olhos vagueiam: a "pensar"
    "processing": [
        _com(olhos=OLHOS_ESQ), _com(),
        _com(olhos=OLHOS_DIR), _com(),
    ],
    # boca abre/fecha
    "speaking": [
        _com(boca=BOCA_ABERTA),
        _com(),
    ],
}

# Animações raras de idle: correm uma passagem e voltam ao loop normal.
EXTRAS = {
    "olhar": [
        _com(olhos=OLHOS_ESQ), _com(olhos=OLHOS_ESQ),
        _com(olhos=OLHOS_DIR), _com(olhos=OLHOS_DIR),
        _com(),
    ],
    "dormir": [_com(olhos=OLHOS_FECHADOS)] * 6,
    "salto": [_com(desce=1), _com(), _com(desce=1)],
}
