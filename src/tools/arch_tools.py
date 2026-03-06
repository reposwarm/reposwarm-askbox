"""Strands agent tools for querying the arch-hub."""

import json
from strands import tool

# The arch_hub instance is set by the agent module before tools are used
_arch_hub = None


def set_arch_hub(hub):
    """Set the global arch-hub instance for tools to use."""
    global _arch_hub
    _arch_hub = hub


@tool
def list_repos() -> str:
    """List all repositories in the arch-hub with their summaries and available sections.
    
    Call this first to understand what repos are available before reading specific files.
    Returns a JSON manifest of all repos with name, summary, sections, and line count.
    """
    if not _arch_hub:
        return "Error: arch-hub not loaded"
    
    manifest = _arch_hub.get_manifest()
    return json.dumps(manifest, indent=2)


@tool
def read_arch(repo: str, section: str = "") -> str:
    """Read architecture documentation for a specific repository.
    
    Args:
        repo: Repository name (e.g., 'express', 'react', 'my-api')
        section: Optional section name to read (e.g., 'hl_overview', 'dependencies', 'security_check').
                 If empty, returns the full arch file.
    
    Returns the content of the arch file or section. Use list_repos() first to see available repos and sections.
    """
    if not _arch_hub:
        return "Error: arch-hub not loaded"
    
    sec = section if section else None
    content = _arch_hub.read_arch(repo, sec)
    
    if content is None:
        available = list(_arch_hub.repos.keys())
        if repo not in available:
            return f"Error: repo '{repo}' not found. Available repos: {', '.join(available)}"
        return f"Error: section '{section}' not found in {repo}"
    
    return content


@tool
def search_arch(query: str, max_results: int = 20) -> str:
    """Search across all architecture files for a text query.
    
    Args:
        query: Search string (case-insensitive)
        max_results: Maximum number of results to return (default 20)
    
    Returns matching lines with surrounding context from across all repos.
    Useful for finding which repos mention a specific technology, pattern, or concept.
    """
    if not _arch_hub:
        return "Error: arch-hub not loaded"
    
    results = _arch_hub.search(query, max_results)
    
    if not results:
        return f"No results found for '{query}'"
    
    output_parts = []
    for r in results:
        output_parts.append(f"### {r['repo']} (line {r['line']})\n{r['context']}")
    
    return f"Found {len(results)} matches for '{query}':\n\n" + "\n\n---\n\n".join(output_parts)
