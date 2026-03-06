"""Claude Agent SDK adapter — uses built-in Read/Glob/Grep tools."""

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from src.adapters import AgentAdapter


class ClaudeAgentAdapter(AgentAdapter):
    """Agent adapter using the Claude Agent SDK.

    The SDK provides built-in file reading, glob, grep, and bash tools.
    The agent explores the arch-hub directory autonomously — no custom tools needed.
    """

    def __init__(self, model: str | None = None, max_turns: int = 50):
        self.model = model
        self.max_turns = max_turns

    async def ask(
        self,
        question: str,
        arch_hub_path: str,
        system_prompt: str,
        on_status: callable = None,
    ) -> str:
        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep"],
            permission_mode="bypassPermissions",
            system_prompt=system_prompt,
            cwd=arch_hub_path,
            max_turns=self.max_turns,
        )
        if self.model:
            options.model = self.model

        result_text = ""
        tool_calls = 0

        async for message in query(prompt=question, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "name"):
                        tool_calls += 1
                        if on_status:
                            on_status(f"Tool: {block.name} (call #{tool_calls})")
            elif isinstance(message, ResultMessage):
                result_text = message.result if hasattr(message, "result") else ""

        if not result_text:
            return "Error: Agent completed without producing a result."

        return result_text
