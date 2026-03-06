"""RepoSwarm Askbox — AI agent that answers architecture questions across repos."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from src.arch_hub import ArchHub
from src.tools.arch_tools import list_repos, read_arch, search_arch, set_arch_hub


SYSTEM_PROMPT = """You are an expert software architect analyzing a portfolio of repositories.

You have access to an arch-hub — a collection of .arch.md architecture documentation files, 
one per repository. Each file contains standardized sections covering high-level overview, 
module deep dives, dependencies, security, testing patterns, and more.

Your job is to answer architecture questions by reading and reasoning across these files.

## How to work:

1. **Start with list_repos()** to see all available repos and their summaries.
2. **Read relevant arch files** using read_arch(repo) or read_arch(repo, section) for specific sections.
3. **Search across repos** using search_arch(query) when looking for specific technologies or patterns.
4. **Reason across repos** — your unique value is connecting information across multiple repos.
5. **Be specific** — cite which repos and sections your conclusions come from.

## Answer format:

Write your answer as clear, well-structured markdown. Include:
- A brief summary at the top
- Detailed analysis with evidence from the arch files
- Which repos you analyzed and why
- Any caveats or gaps in the available documentation

## Rules:
- Only reference repos that exist in the arch-hub. Never hallucinate repo names.
- If the arch files don't contain enough info to answer, say so clearly.
- Be thorough but concise. Quality over length.
"""


def create_agent(model_id: str | None = None):
    """Create the Strands agent with arch-hub tools."""
    from strands import Agent

    # Determine provider and model
    use_bedrock = os.environ.get("CLAUDE_CODE_USE_BEDROCK") == "1"
    litellm_url = os.environ.get("LITELLM_API_URL")
    
    if use_bedrock:
        from strands.models.bedrock import BedrockModel
        model = BedrockModel(
            model_id=model_id or os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
    elif litellm_url:
        from strands.models.litellm import LiteLLMModel
        model = LiteLLMModel(
            model_id=model_id or os.environ.get("MODEL_ID", "claude-sonnet-4-20250514"),
            api_base=litellm_url,
            api_key=os.environ.get("LITELLM_API_KEY", ""),
        )
    else:
        from strands.models.anthropic import AnthropicModel
        model = AnthropicModel(
            model_id=model_id or os.environ.get("MODEL_ID", "claude-sonnet-4-20250514"),
        )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[list_repos, read_arch, search_arch],
    )
    
    return agent


def write_status(msg: str, status_file: str | None = None):
    """Write a status/progress update."""
    print(f"[askbox] {msg}", flush=True)
    if status_file:
        Path(status_file).write_text(json.dumps({
            "detail": msg,
            "timestamp": time.time(),
        }))


def run_question(
    question: str,
    arch_hub_url: str,
    arch_hub_branch: str = "main",
    output_dir: str = "/output",
    status_file: str | None = None,
    repos_filter: list[str] | None = None,
    model_id: str | None = None,
    max_tool_calls: int = 50,
) -> str:
    """Run a question against the arch-hub and return the answer."""
    
    # Step 1: Clone arch-hub
    write_status("Cloning arch-hub...", status_file)
    hub = ArchHub()
    hub.clone(arch_hub_url, arch_hub_branch)
    
    # Step 2: Load and index
    write_status("Loading architecture files...", status_file)
    hub.load(repos_filter)
    write_status(f"Loaded {len(hub.repos)} architecture files", status_file)
    
    if not hub.repos:
        error = "No architecture files found in arch-hub"
        write_status(f"Error: {error}", status_file)
        return error
    
    # Step 3: Set up tools
    set_arch_hub(hub)
    
    # Step 4: Run agent
    write_status("Running agent...", status_file)
    agent = create_agent(model_id)
    
    result = agent(question)
    answer = str(result)
    
    # Step 5: Write output
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    answer_file = output_path / "answer.md"
    answer_file.write_text(answer, encoding="utf-8")
    
    write_status(f"Answer written to {answer_file} ({len(answer)} chars)", status_file)
    
    return answer


def main():
    """Entry point — reads config from env vars or CLI args."""
    parser = argparse.ArgumentParser(description="RepoSwarm Askbox — query architecture docs with AI")
    parser.add_argument("--question", "-q", help="Question to ask")
    parser.add_argument("--arch-hub-url", help="Git URL of arch-hub repo")
    parser.add_argument("--arch-hub-branch", default="main", help="Branch to clone")
    parser.add_argument("--output-dir", default="/output", help="Output directory")
    parser.add_argument("--repos", help="Comma-separated list of repos to scope to")
    parser.add_argument("--model", help="Model ID override")
    parser.add_argument("--max-tool-calls", type=int, default=50, help="Max agent tool calls")
    args = parser.parse_args()
    
    question = args.question or os.environ.get("QUESTION")
    arch_hub_url = args.arch_hub_url or os.environ.get("ARCH_HUB_URL")
    arch_hub_branch = args.arch_hub_branch or os.environ.get("ARCH_HUB_BRANCH", "main")
    output_dir = args.output_dir or os.environ.get("OUTPUT_DIR", "/output")
    status_file = os.environ.get("STATUS_FILE")
    model_id = args.model or os.environ.get("MODEL_ID")
    max_tool_calls = args.max_tool_calls or int(os.environ.get("MAX_TOOL_CALLS", "50"))
    
    repos_filter = None
    repos_str = args.repos or os.environ.get("REPOS_FILTER")
    if repos_str:
        repos_filter = [r.strip() for r in repos_str.split(",")]
    
    if not question:
        print("Error: QUESTION env var or --question flag required", file=sys.stderr)
        sys.exit(1)
    if not arch_hub_url:
        print("Error: ARCH_HUB_URL env var or --arch-hub-url flag required", file=sys.stderr)
        sys.exit(1)
    
    try:
        answer = run_question(
            question=question,
            arch_hub_url=arch_hub_url,
            arch_hub_branch=arch_hub_branch,
            output_dir=output_dir,
            status_file=status_file,
            repos_filter=repos_filter,
            model_id=model_id,
            max_tool_calls=max_tool_calls,
        )
        print(f"\n{'='*60}")
        print("ANSWER:")
        print(f"{'='*60}\n")
        print(answer)
    except Exception as e:
        write_status(f"Failed: {e}", status_file)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
