"""Arch-hub management — clone, load, and index architecture files."""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoInfo:
    """Metadata about a single repo's architecture file."""
    name: str
    file_path: str
    sections: list[str] = field(default_factory=list)
    summary: str = ""
    line_count: int = 0
    size_bytes: int = 0


class ArchHub:
    """Manages a local clone of the arch-hub repository."""

    def __init__(self, path: str = "/tmp/arch-hub"):
        self.path = Path(path)
        self.repos: dict[str, RepoInfo] = {}
        self._loaded = False

    def clone(self, url: str, branch: str = "main") -> None:
        """Clone (or pull) the arch-hub repo."""
        # Inject GitHub token if available (for private repos)
        auth_url = self._inject_auth(url)

        if (self.path / ".git").exists():
            subprocess.run(
                ["git", "-C", str(self.path), "pull", "--ff-only"],
                capture_output=True, text=True, check=True
            )
        else:
            self.path.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", branch, auth_url, str(self.path)],
                capture_output=True, text=True, check=True
            )
            # Strip credentials from stored remote URL
            subprocess.run(
                ["git", "-C", str(self.path), "remote", "set-url", "origin", url],
                capture_output=True, text=True
            )

    @staticmethod
    def _inject_auth(url: str) -> str:
        """Inject GITHUB_TOKEN into URL for private repo access."""
        token = os.environ.get("GITHUB_TOKEN", "")
        if token and "github.com" in url and "x-access-token" not in url:
            return url.replace("https://", f"https://x-access-token:{token}@")
        return url

    def load(self, repos_filter: list[str] | None = None) -> None:
        """Load and index all .arch.md files."""
        self.repos = {}
        for f in sorted(self.path.glob("*.arch.md")):
            name = f.stem.removesuffix(".arch")
            if repos_filter and name not in repos_filter:
                continue

            content = f.read_text(encoding="utf-8", errors="replace")
            sections = self._extract_sections(content)
            summary = self._extract_summary(content)

            self.repos[name] = RepoInfo(
                name=name,
                file_path=str(f),
                sections=sections,
                summary=summary,
                line_count=content.count("\n") + 1,
                size_bytes=f.stat().st_size,
            )
        self._loaded = True

    def get_manifest(self) -> list[dict]:
        """Return a manifest of all repos with metadata."""
        return [
            {
                "name": r.name,
                "summary": r.summary,
                "sections": r.sections,
                "lines": r.line_count,
            }
            for r in self.repos.values()
        ]

    def read_arch(self, repo: str, section: str | None = None) -> str | None:
        """Read a repo's arch file, optionally a specific section."""
        info = self.repos.get(repo)
        if not info:
            return None

        content = Path(info.file_path).read_text(encoding="utf-8", errors="replace")

        if section:
            return self._extract_section_content(content, section)

        return content

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Search across all arch files for a query string."""
        results = []
        query_lower = query.lower()

        for repo_info in self.repos.values():
            content = Path(repo_info.file_path).read_text(
                encoding="utf-8", errors="replace"
            )
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    # Get context: 2 lines before and after
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context = "\n".join(lines[start:end])
                    results.append({
                        "repo": repo_info.name,
                        "line": i + 1,
                        "match": line.strip(),
                        "context": context,
                    })
                    if len(results) >= max_results:
                        return results

        return results

    def _extract_sections(self, content: str) -> list[str]:
        """Extract section names (# headers) from arch file."""
        sections = []
        for line in content.split("\n"):
            if line.startswith("# ") and not line.startswith("# Repository"):
                section_name = line[2:].strip()
                sections.append(section_name)
        return sections

    def _extract_summary(self, content: str) -> str:
        """Extract a one-line summary from the arch file."""
        # Look for Project Purpose or first meaningful paragraph after hl_overview
        in_overview = False
        for line in content.split("\n"):
            if "## Project Purpose" in line or "## Overview" in line:
                in_overview = True
                continue
            if in_overview and line.strip() and not line.startswith("#"):
                # Return first non-empty line after the header
                return line.strip()[:200]
            if in_overview and line.startswith("#"):
                break

        # Fallback: first non-header, non-empty line
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                return stripped[:200]

        return ""

    def _extract_section_content(self, content: str, section: str) -> str | None:
        """Extract content of a specific section from an arch file."""
        lines = content.split("\n")
        section_lower = section.lower()
        capturing = False
        result_lines = []

        for line in lines:
            if line.startswith("# ") and section_lower in line.lower():
                capturing = True
                result_lines.append(line)
                continue
            if capturing:
                if line.startswith("# ") and section_lower not in line.lower():
                    break
                result_lines.append(line)

        return "\n".join(result_lines) if result_lines else None
