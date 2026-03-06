"""Tests for the ArchHub class — loading, indexing, searching arch files."""

import os
import tempfile
from pathlib import Path

import pytest

from src.arch_hub import ArchHub


SAMPLE_ARCH = """# hl_overview

High level overview of the codebase

## Project Purpose
A sample REST API for managing users and billing.

## Architecture Pattern
Microservice with event-driven components.

## Technology Stack
- Node.js 22, TypeScript 5.4
- Express 5, Prisma 6.2
- PostgreSQL, Redis

# dependencies

## External Services
- billing-service: REST API (POST /charge)
- user-db: PostgreSQL shared schema
- cache: Redis cluster

## Key Libraries
- express ^5.0
- prisma ^6.2
- zod ^3.22

# security_check

## Authentication
JWT validation on all routes via middleware/auth.ts.
Rate limiting: 100 req/min per IP.

# module_deep_dive

## src/routes/
14 route handlers covering users, billing, and admin.

## src/services/
Business logic layer. Billing sync, user management.
"""

SAMPLE_ARCH_2 = """# hl_overview

## Project Purpose
React SPA frontend consuming the my-api REST endpoints.

## Technology Stack
- React 19, TypeScript
- Vite, TailwindCSS

# dependencies

## External Services
- my-api: REST API (all /api/* endpoints)
- auth: Cognito JWT tokens

# security_check

## Authentication
JWT tokens stored in httpOnly cookies. Refresh via /auth/refresh.
"""


@pytest.fixture
def arch_hub_dir():
    """Create a temp directory with sample arch files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "my-api.arch.md").write_text(SAMPLE_ARCH)
        Path(tmpdir, "my-frontend.arch.md").write_text(SAMPLE_ARCH_2)
        Path(tmpdir, "README.md").write_text("# Arch Hub\nSample results.")
        yield tmpdir


@pytest.fixture
def hub(arch_hub_dir):
    """Create an ArchHub instance loaded with sample data."""
    h = ArchHub(arch_hub_dir)
    h.load()
    return h


class TestLoad:
    def test_loads_arch_files(self, hub):
        assert len(hub.repos) == 2
        assert "my-api" in hub.repos
        assert "my-frontend" in hub.repos

    def test_ignores_non_arch_files(self, hub):
        # README.md should not be loaded
        assert "README" not in hub.repos

    def test_extracts_sections(self, hub):
        sections = hub.repos["my-api"].sections
        assert "hl_overview" in sections
        assert "dependencies" in sections
        assert "security_check" in sections
        assert "module_deep_dive" in sections

    def test_extracts_summary(self, hub):
        summary = hub.repos["my-api"].summary
        assert "REST API" in summary or "sample" in summary.lower()

    def test_line_count(self, hub):
        assert hub.repos["my-api"].line_count > 10
        assert hub.repos["my-frontend"].line_count > 5

    def test_size_bytes(self, hub):
        assert hub.repos["my-api"].size_bytes > 0

    def test_repos_filter(self, arch_hub_dir):
        h = ArchHub(arch_hub_dir)
        h.load(repos_filter=["my-api"])
        assert len(h.repos) == 1
        assert "my-api" in h.repos
        assert "my-frontend" not in h.repos

    def test_repos_filter_no_match(self, arch_hub_dir):
        h = ArchHub(arch_hub_dir)
        h.load(repos_filter=["nonexistent"])
        assert len(h.repos) == 0


class TestManifest:
    def test_manifest_structure(self, hub):
        manifest = hub.get_manifest()
        assert len(manifest) == 2
        
        entry = next(e for e in manifest if e["name"] == "my-api")
        assert "summary" in entry
        assert "sections" in entry
        assert "lines" in entry
        assert isinstance(entry["sections"], list)
        assert len(entry["sections"]) > 0

    def test_manifest_has_all_repos(self, hub):
        manifest = hub.get_manifest()
        names = [e["name"] for e in manifest]
        assert "my-api" in names
        assert "my-frontend" in names


class TestReadArch:
    def test_read_full_file(self, hub):
        content = hub.read_arch("my-api")
        assert content is not None
        assert "hl_overview" in content
        assert "dependencies" in content
        assert "security_check" in content

    def test_read_specific_section(self, hub):
        content = hub.read_arch("my-api", "security_check")
        assert content is not None
        assert "JWT validation" in content
        assert "Rate limiting" in content
        # Should not contain other sections
        assert "Key Libraries" not in content

    def test_read_dependencies_section(self, hub):
        content = hub.read_arch("my-api", "dependencies")
        assert content is not None
        assert "billing-service" in content
        assert "prisma" in content

    def test_read_nonexistent_repo(self, hub):
        content = hub.read_arch("nonexistent")
        assert content is None

    def test_read_nonexistent_section(self, hub):
        content = hub.read_arch("my-api", "nonexistent_section")
        assert content is None


class TestSearch:
    def test_search_finds_matches(self, hub):
        results = hub.search("billing")
        assert len(results) > 0
        repos_found = {r["repo"] for r in results}
        assert "my-api" in repos_found

    def test_search_case_insensitive(self, hub):
        results = hub.search("JWT")
        assert len(results) > 0
        results2 = hub.search("jwt")
        assert len(results2) > 0

    def test_search_across_repos(self, hub):
        results = hub.search("authentication")
        repos_found = {r["repo"] for r in results}
        # Both repos mention auth
        assert len(repos_found) >= 1

    def test_search_returns_context(self, hub):
        results = hub.search("billing-service")
        assert len(results) > 0
        assert "context" in results[0]
        assert len(results[0]["context"]) > len(results[0]["match"])

    def test_search_max_results(self, hub):
        results = hub.search("e", max_results=3)  # 'e' matches almost everything
        assert len(results) <= 3

    def test_search_no_results(self, hub):
        results = hub.search("xyznonexistent12345")
        assert len(results) == 0

    def test_search_result_has_repo_and_line(self, hub):
        results = hub.search("Express")
        assert len(results) > 0
        assert "repo" in results[0]
        assert "line" in results[0]
        assert isinstance(results[0]["line"], int)


class TestClone:
    def test_clone_real_repo(self, tmp_path):
        """Integration test — actually clones the sample arch-hub."""
        hub = ArchHub(str(tmp_path / "arch-hub"))
        hub.clone("https://github.com/royosherove/repo-swarm-sample-results-hub.git")
        hub.load()
        
        assert len(hub.repos) > 5
        assert "react" in hub.repos or "express" in hub.repos
        
        # Verify manifest works
        manifest = hub.get_manifest()
        assert len(manifest) > 5
        
        # Verify search works
        results = hub.search("TypeScript")
        assert len(results) > 0
