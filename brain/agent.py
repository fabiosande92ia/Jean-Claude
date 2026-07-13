# brain/agent.py
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock, SdkPluginConfig,
    StreamEvent,
)
from core import config
from brain.tools import screenshot_server, JC_TOOL_NAMES


class JeanClaude:
    """Cérebro do Jean Claude: wrapper isolado do Claude Agent SDK."""

    def __init__(self, extra_tools=None):
        self.extra_tools = extra_tools or []

    def _system_prompt(self) -> str:
        return config.CLAUDE_MD.read_text(encoding="utf-8")

    def build_options(self) -> ClaudeAgentOptions:
        # Estilo caveman: plugin real, o mesmo do Claude Code do Fábio. Nível
        # fixo em ultra via env (só neste subprocess). Plugin ausente = fala normal.
        plugins: list[SdkPluginConfig] = []
        caveman = config.caveman_plugin_path()
        if caveman:
            plugins.append(SdkPluginConfig(type="local", path=str(caveman)))
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            allowed_tools=list(config.ALLOWED_TOOLS) + list(JC_TOOL_NAMES) + list(self.extra_tools),
            mcp_servers={"jc": screenshot_server},
            # Config isolada SÓ no subprocess do SDK (o transport faz merge de
            # os.environ + isto). Antes era os.environ["CLAUDE_CONFIG_DIR"]=...,
            # que contaminava o processo todo: qualquer coisa que a app lançasse
            # depois — a consola do abrir_consola, por exemplo — herdava a config
            # isolada e abria sem os plugins/skills globais do Fábio.
            env={
                "CLAUDE_CONFIG_DIR": str(config.CONFIG_DIR),
                "CAVEMAN_DEFAULT_MODE": config.CAVEMAN_MODE,
            },
            plugins=plugins,
            setting_sources=[],            # NÃO herdar settings globais do utilizador
            cwd=str(config.PROJECT_ROOT),
            permission_mode="acceptEdits", # v1: autónomo no projeto
            include_partial_messages=True, # liga o streaming: StreamEvent chega no ask()
            # Default do SDK é 1MB e cabe só a stdout do processo CLI (resultados de
            # Read/Bash/Grep, não o que nós enviamos). Um ficheiro grande lido pela
            # tool Read já estoura isso. 20MB dá margem sem deixar de apanhar um
            # runaway genuíno.
            max_buffer_size=20 * 1024 * 1024,
        )

    async def ask(self, prompt: str, on_delta=None) -> str:
        """Envia prompt ao cérebro, devolve o texto final da resposta.

        `on_delta`, se dado, é chamado com cada pedaço de texto à medida que
        chega (via StreamEvent). O retorno continua a ser o texto completo,
        montado a partir do AssistantMessage final — não da soma dos deltas.
        """
        reply = []
        async with ClaudeSDKClient(options=self.build_options()) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            reply.append(block.text)
                elif isinstance(msg, StreamEvent) and on_delta is not None:
                    delta = msg.event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        pedaco = delta.get("text", "")
                        if pedaco:
                            on_delta(pedaco)
        return "".join(reply).strip()
