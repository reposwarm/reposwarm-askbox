"""Agent adapter interface — abstracts the LLM agent backend."""

from abc import ABC, abstractmethod


class AgentAdapter(ABC):
    """Interface for agent backends that answer questions about arch files."""

    @abstractmethod
    async def ask(
        self,
        question: str,
        arch_hub_path: str,
        system_prompt: str,
        on_status: callable = None,
    ) -> str:
        """Run the agent against the arch-hub and return the answer as markdown.

        Args:
            question: The architecture question to answer.
            arch_hub_path: Local path to the cloned arch-hub directory.
            system_prompt: System prompt for the agent.
            on_status: Optional callback for progress updates, called with (message: str).

        Returns:
            The agent's answer as a markdown string.
        """
        ...
