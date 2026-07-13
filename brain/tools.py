# brain/tools.py
import base64
from claude_agent_sdk import tool, create_sdk_mcp_server
from vision import screen

SCREENSHOT_TOOL_NAME = "mcp__jc__screenshot"


@tool("screenshot", "Captura o ecrã atual do Fábio e devolve a imagem para o Jean Claude ver.", {})
async def screenshot(args):
    jpeg = screen.capture_jpeg()
    b64 = base64.standard_b64encode(jpeg).decode("ascii")
    return {
        "content": [
            {"type": "image", "data": b64, "mimeType": "image/jpeg"}
        ]
    }


screenshot_server = create_sdk_mcp_server(name="jc", version="1.0.0", tools=[screenshot])
