# brain/agent.py
import os
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock
from core import config


class JeanClaude:
    """Cérebro do Jean Claude: wrapper isolado do Claude Agent SDK."""

    def __init__(self, extra_tools=None):
        self.extra_tools = extra_tools or []
        # isola a config: SDK usa o CLAUDE_CONFIG_DIR próprio
        os.environ["CLAUDE_CONFIG_DIR"] = str(config.CONFIG_DIR)

    def _system_prompt(self) -> str:
        return config.CLAUDE_MD.read_text(encoding="utf-8")

    def build_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(),
            allowed_tools=list(config.ALLOWED_TOOLS) + list(self.extra_tools),
            setting_sources=[],            # NÃO herdar settings globais do utilizador
            cwd=str(config.PROJECT_ROOT),
            permission_mode="acceptEdits", # v1: autónomo no projeto
        )

    async def ask(self, prompt: str) -> str:
        """Envia prompt ao cérebro, devolve o texto final da resposta."""
        reply = []
        async with ClaudeSDKClient(options=self.build_options()) as client:
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            reply.append(block.text)
        return "".join(reply).strip()
