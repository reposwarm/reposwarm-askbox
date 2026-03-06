"""Strands SDK adapter — uses custom arch-hub tools."""

import os
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands.models.anthropic import AnthropicModel

from src.adapters import AgentAdapter
from src.arch_hub import ArchHub


# Module-level arch hub reference for tools
_hub: ArchHub | None = None


@tool
def list_repos() -> str:
    """List all repositories in the arch-hub with their summaries and available sections.
    Call this first to understand what repos are available before reading specific files.
    Returns a JSON manifest of all repos with name, summary, sections, and line count."""
    import json
    if not _hub:
        return "Error: arch-hub not loaded"
    return json.dumps(_hub.get_manifest(), indent=2)


@tool
def read_arch(repo: str, section: str = "") -> str:
    """Read architecture documentation for a specific repository.
    Args:
        repo: Repository name (e.g., 'express', 'react', 'my-api')
        section: Optional section name to read (e.g., 'hl_overview', 'dependencies').
                 If empty, returns the full arch file.
    Use list_repos() first to see available repos and sections."""
    if not _hub:
        return "Error: arch-hub not loaded"
    sec = section if section else None
    content = _hub.read_arch(repo, sec)
    if content is None:
        available = list(_hub.repos.keys())
        if repo not in available:
            return f"Error: repo '{repo}' not found. Available: {', '.join(available)}"
        return f"Error: section '{section}' not found in {repo}"
    return content


@tool
def search_arch(query: str, max_results: int = 20) -> str:
    """Search across all architecture files for a text query.
    Args:
        query: Search string (case-insensitive)
        max_results: Maximum number of results to return (default 20)
    Returns matching lines with surrounding context from across all repos."""
    if not _hub:
        return "Error: arch-hub not loaded"
    results = _hub.search(query, max_results)
    if not results:
        return f"No results found for '{query}'"
    parts = [f"### {r['repo']} (line {r['line']})\n{r['context']}" for r in results]
    return f"Found {len(results)} matches:\n\n" + "\n\n---\n\n".join(parts)


class StrandsAdapter(AgentAdapter):
    """Agent adapter using the Strands SDK with custom arch-hub tools.

    Requires explicit tool definitions but supports any LLM provider
    (Anthropic, Bedrock, LiteLLM) via Strands model classes.
    """

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id

    async def ask(
        self,
        question: str,
        arch_hub_path: str,
        system_prompt: str,
        on_status: callable = None,
    ) -> str:
        global _hub
        
        # Load arch-hub
        if on_status:
            on_status("Loading architecture files...")
        hub = ArchHub(arch_hub_path)
        hub.load()
        _hub = hub

        if on_status:
            on_status(f"Loaded {len(hub.repos)} architecture files")

        # Determine model
        use_bedrock = os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1"
        if use_bedrock:
            model = BedrockModel(
                model_id=self.model_id or os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
        else:
            model = AnthropicModel(
                model_id=self.model_id or os.environ.get("MODEL_ID", "claude-sonnet-4-20250514"),
            )

        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[list_repos, read_arch, search_arch],
        )

        if on_status:
            on_status("Running agent...")

        result = agent(question)
        return str(result)
