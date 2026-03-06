"""RepoSwarm Askbox — AI agent that answers architecture questions across repos."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from src.adapters import AgentAdapter


SYSTEM_PROMPT = """You are an expert software architect analyzing a portfolio of repositories.

You have access to an arch-hub directory containing .arch.md architecture documentation files,
one per repository. Each file contains standardized sections covering high-level overview,
module deep dives, dependencies, security, testing patterns, and more.

Your job is to answer architecture questions by reading and reasoning across these files.

## How to work:

1. **Start by listing files** to see all available .arch.md files and understand the portfolio.
2. **Read relevant arch files** — focus on repos most relevant to the question.
3. **Search across files** when looking for specific technologies, patterns, or concepts.
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


def clone_arch_hub(url: str, path: str, branch: str = "main") -> None:
    """Clone or pull the arch-hub repository."""
    target = Path(path)
    if (target / ".git").exists():
        subprocess.run(
            ["git", "-C", str(target), "pull", "--ff-only"],
            capture_output=True, text=True, check=True,
        )
    else:
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "-b", branch, url, str(target)],
            capture_output=True, text=True, check=True,
        )


def get_adapter(adapter_name: str, model: str | None = None) -> AgentAdapter:
    """Factory function to create the appropriate agent adapter."""
    if adapter_name == "claude-agent-sdk":
        from src.adapters.claude_agent import ClaudeAgentAdapter
        return ClaudeAgentAdapter(model=model)
    elif adapter_name == "strands":
        from src.adapters.strands_adapter import StrandsAdapter
        return StrandsAdapter(model_id=model)
    else:
        raise ValueError(f"Unknown adapter: {adapter_name}. Use 'claude-agent-sdk' or 'strands'.")


def write_status(msg: str, status_file: str | None = None):
    """Write a status/progress update."""
    print(f"[askbox] {msg}", flush=True)
    if status_file:
        Path(status_file).write_text(json.dumps({
            "detail": msg,
            "timestamp": time.time(),
        }))


async def run_question(
    question: str,
    arch_hub_url: str,
    arch_hub_branch: str = "main",
    arch_hub_path: str = "/tmp/arch-hub",
    output_dir: str = "/output",
    status_file: str | None = None,
    adapter_name: str = "claude-agent-sdk",
    model: str | None = None,
) -> str:
    """Run a question against the arch-hub and return the answer."""

    # Step 1: Clone arch-hub
    write_status("Cloning arch-hub...", status_file)
    clone_arch_hub(arch_hub_url, arch_hub_path, arch_hub_branch)
    write_status("Arch-hub ready", status_file)

    # Step 2: Create adapter
    adapter = get_adapter(adapter_name, model)
    write_status(f"Using adapter: {adapter_name}", status_file)

    # Step 3: Run agent
    def on_status(msg):
        write_status(msg, status_file)

    answer = await adapter.ask(
        question=question,
        arch_hub_path=arch_hub_path,
        system_prompt=SYSTEM_PROMPT,
        on_status=on_status,
    )

    # Step 4: Write output
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
    parser.add_argument("--arch-hub-path", default="/tmp/arch-hub", help="Local clone path")
    parser.add_argument("--output-dir", default="/output", help="Output directory")
    parser.add_argument("--adapter", default="claude-agent-sdk", choices=["claude-agent-sdk", "strands"],
                        help="Agent adapter to use (default: claude-agent-sdk)")
    parser.add_argument("--model", help="Model ID override")
    args = parser.parse_args()

    question = args.question or os.environ.get("QUESTION")
    arch_hub_url = args.arch_hub_url or os.environ.get("ARCH_HUB_URL")
    arch_hub_branch = args.arch_hub_branch or os.environ.get("ARCH_HUB_BRANCH", "main")
    arch_hub_path = args.arch_hub_path or os.environ.get("ARCH_HUB_PATH", "/tmp/arch-hub")
    output_dir = args.output_dir or os.environ.get("OUTPUT_DIR", "/output")
    status_file = os.environ.get("STATUS_FILE")
    adapter_name = args.adapter or os.environ.get("ASKBOX_ADAPTER", "claude-agent-sdk")
    model = args.model or os.environ.get("MODEL_ID")

    if not question:
        print("Error: QUESTION env var or --question flag required", file=sys.stderr)
        sys.exit(1)
    if not arch_hub_url:
        print("Error: ARCH_HUB_URL env var or --arch-hub-url flag required", file=sys.stderr)
        sys.exit(1)

    try:
        answer = asyncio.run(run_question(
            question=question,
            arch_hub_url=arch_hub_url,
            arch_hub_branch=arch_hub_branch,
            arch_hub_path=arch_hub_path,
            output_dir=output_dir,
            status_file=status_file,
            adapter_name=adapter_name,
            model=model,
        ))
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
