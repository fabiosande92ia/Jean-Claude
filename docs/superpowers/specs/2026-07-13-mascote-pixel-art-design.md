# Mascote pixel art do Jean Claude — design

Data: 2026-07-13
Estado: aprovado em conversa, pendente revisão do spec

## Objetivo

Mascote pixel art viva no ambiente de trabalho: janela transparente sem moldura,
sempre por cima, animada conforme o estado do Jean Claude. Dá presença ao
assistente mesmo com a janela de chat fechada/minimizada.

## Design visual (aprovado)

Híbrido blob laranja + robô retro:

- Corpo: blob laranja arredondado (`#D97757`, família Claude), braços curtos,
  dois pés, linha de sombra na base (`#bd5f3c`, pés `#A6552F`).
- Antena no topo: haste `#A6552F`, ponta vermelha `#e35d4f`.
- Visor escuro (`#1c2b33`) no lugar da cara, com dois olhos ciano (`#59e3d8`).
- Sem elementos caveman (decidido: retirados).

Grelha base 16×16 células, escala 4 → 64×64 px no ecrã. Pixels duros, sem
anti-aliasing — é o que torna a transparência por cor-chave invisível.

## Decisões de produto

| Decisão | Valor |
|---|---|
| Janela | própria, independente do chat |
| Tamanho | ~64 px |
| Animações | pack completo + extras raros no idle |
| Arrastável | sim, posição persiste entre arranques |
| Clique | abre/foca a janela de chat |
| Always-on-top | sim |
| Balão de fala | sim, última resposta curta |

## Arquitetura

### Abordagem técnica

Tkinter `Toplevel` no mesmo processo da UI existente:

- `overrideredirect(True)` — sem moldura.
- `wm_attributes("-transparentcolor", COR_CHAVE)` — cor-chave (magenta
  `#ff00fe`, ausente da paleta da mascote) torna-se transparente e
  click-through no Windows.
- `wm_attributes("-topmost", True)` — sempre por cima.
- Desenho em `tk.Canvas` com fundo na cor-chave; sprites são rects escalados.
- Animação com `root.after()` — mesmo loop do Tk, sem threads novas.

Rejeitado: PySide6 (segundo toolkit + segundo event loop no mesmo processo) e
layered windows win32 (complexidade sem ganho — pixel art não precisa de alpha
parcial).

### Componentes

**`ui/sprites.py` — dados dos sprites (novo)**
- Sprites como grelhas: `dict[str, str]` de paleta (carácter → cor hex) +
  `list[str]` de linhas (um carácter por célula, `.` = transparente).
- Frames nomeados por estado: `FRAMES["idle"] = [frame1, frame2, ...]`, etc.
- Função `validar(frame)` usada nos testes: dimensões consistentes, carateres
  todos na paleta, nenhuma cor igual à cor-chave.
- Sem PNGs externos: editável em texto, testável, zero assets para gerir.

**`ui/mascot.py` — janela e animação (novo)**
- `class Mascot` recebe `root` (Tk), `on_click` (callback para focar chat) e
  lê/grava posição via o padrão existente de `ui.json` (`core.config.UI_STATE_FILE`,
  chave própria `mascot_pos`; validação de que a posição cabe no ecrã reutiliza
  a lógica de `geometry_cabe`).
- API pública:
  - `set_state(estado: str)` — muda a animação corrente (mapa direto dos
    estados do StateBus: `idle`, `loading`, `recording`, `processing`,
    `speaking`; estado desconhecido cai em `idle`).
  - `balao(texto: str)` — mostra balão de fala.
  - `destroy()` — limpeza no fecho da app.
- Motor de animação: um `after()` agendado por tick (~150 ms por frame);
  cada estado tem a sua lista de frames em loop.
- Extras raros: em `idle`, a cada tick há probabilidade pequena (~1/200) de
  disparar uma animação especial (olhar à volta, dormir, saltinho) que corre
  uma vez e volta ao loop de idle.
- Arrastar: bindings `<Button-1>`/`<B1-Motion>`/`<ButtonRelease-1>`; um
  movimento abaixo de ~5 px conta como clique (chama `on_click`), acima é
  arrasto. Posição gravada no release.

**Animações por estado**
| Estado | Animação |
|---|---|
| `idle` | respiração (corpo sobe/desce 1 px) + pestanejo ocasional dos olhos |
| `loading` | barra de progresso a varrer o visor |
| `recording` | ponta da antena pisca vermelho, olhos abertos fixos |
| `processing` | olhos rodam/oscilam (pontos a andar no visor) |
| `speaking` | boca no visor abre/fecha em loop |
| extras (idle) | olhar à volta, dormir (zZ), saltinho — raros, uma passagem |

**Balão de fala**
- Retângulo pixel-art (mesmo estilo, borda escura) ancorado ao lado da mascote,
  desenhado dentro da mesma janela transparente (a janela cresce para o
  acomodar; o canvas cobre mascote + balão).
- Mostra a resposta final do assistente truncada (~120 caracteres + "…").
- Desaparece ao fim de ~6 s ou ao clicar.
- Texto com fonte pequena legível (a fonte não é pixel art — legibilidade
  primeiro).

### Integração (alterações a ficheiros existentes)

- `ui/app.py`: `App.__init__` cria `Mascot(root, on_click=self._mostrar)`.
  No `_poll`: branch `state` chama também `self.mascot.set_state(payload)`;
  branch `assistant` chama `self.mascot.balao(payload)`. `_handle_close`
  chama `self.mascot.destroy()`.
- `core/config.py`: constante `MASCOT` (tamanho/escala) se necessário — mínimo.

### Fluxo de dados

StateBus (worker/hotkey threads) → `ui_queue` → `App._poll` (thread do Tk) →
`Mascot.set_state` / `Mascot.balao`. A mascote nunca toca no StateBus nem em
threads: recebe tudo já na thread do Tk, como o resto da UI.

## Tratamento de erros

- `-transparentcolor` indisponível (Tk antigo/plataforma): mascote não abre,
  log de aviso, app segue sem ela. Nunca bloquear o arranque.
- Posição gravada fora do ecrã (monitor removido): repor posição padrão
  (canto inferior direito com margem).
- `ui.json` corrompido: já tratado pelo padrão existente; a mascote usa o
  mesmo caminho tolerante.

## Testes

- `tests/test_sprites.py`: todos os frames validam (dimensões, paleta,
  sem cor-chave); todos os estados do StateBus têm frames.
- `tests/test_mascot.py` (lógica pura, sem abrir janelas reais, padrão dos
  testes de UI existentes):
  - `set_state` com estado desconhecido cai em idle.
  - clique vs. arrasto: limiar de 5 px.
  - truncagem do balão.
  - persistência de posição (mock de `UI_STATE_FILE`).
  - ciclo de frames avança e faz loop.

## Fora de âmbito

- Sons da mascote.
- Sincronização da boca com o áudio TTS real (a boca mexe enquanto
  `speaking`, não por fonema).
- Interações extra (menu de contexto, alimentar a mascote, etc.).
