"""Tests for the askbox HTTP server."""

import asyncio
import os
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Set env vars before importing server
os.environ["ARCH_HUB_URL"] = ""  # skip clone on startup
os.environ["ASKBOX_PORT"] = "8082"


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_returns_200(self):
        from src.server import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "arch_hub_ready" in data
        assert "uptime_seconds" in data
        assert "jobs_total" in data

    def test_health_shows_arch_hub_not_ready_without_url(self):
        from src.server import app
        client = TestClient(app)
        resp = client.get("/health")
        data = resp.json()
        # No ARCH_HUB_URL set, so arch_hub_ready should be False
        assert data["arch_hub_ready"] is False


class TestAskEndpoint:
    """Test /ask endpoints."""

    def test_ask_returns_503_without_arch_hub(self):
        from src.server import app
        client = TestClient(app)
        resp = client.post("/ask", json={"question": "What is this?"})
        assert resp.status_code == 503
        assert "Arch-hub not loaded" in resp.json()["detail"]

    def test_ask_queues_job_when_ready(self):
        from src import server
        from src.server import app

        # Simulate arch-hub being ready
        server.arch_hub_ready = True
        server.arch_hub_repo_count = 5

        with patch("src.server._run_job", new_callable=AsyncMock) as mock_run:
            client = TestClient(app)
            resp = client.post("/ask", json={"question": "What repos exist?"})
            assert resp.status_code == 200
            data = resp.json()
            assert "id" in data
            assert data["status"] == "queued"

            # Job should exist in store
            job_id = data["id"]
            resp2 = client.get(f"/ask/{job_id}")
            assert resp2.status_code == 200
            assert resp2.json()["question"] == "What repos exist?"

        # Reset
        server.arch_hub_ready = False

    def test_get_unknown_job_returns_404(self):
        from src.server import app
        client = TestClient(app)
        resp = client.get("/ask/nonexistent")
        assert resp.status_code == 404

    def test_list_jobs(self):
        from src import server
        from src.server import app, AskJob, AskStatus

        server.arch_hub_ready = True
        # Add some test jobs
        server.jobs["test1"] = AskJob(
            id="test1", question="Q1", status=AskStatus.completed,
            adapter="claude-agent-sdk", created_at=time.time() - 100,
            answer="Answer 1", completed_at=time.time(),
        )
        server.jobs["test2"] = AskJob(
            id="test2", question="Q2", status=AskStatus.running,
            adapter="claude-agent-sdk", created_at=time.time(),
        )

        client = TestClient(app)
        resp = client.get("/ask")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

        # Filter by status
        resp2 = client.get("/ask?status=running")
        assert resp2.status_code == 200
        running = resp2.json()
        assert all(j["status"] == "running" for j in running)

        # Cleanup
        del server.jobs["test1"]
        del server.jobs["test2"]
        server.arch_hub_ready = False


class TestArchHubRefresh:
    """Test /arch-hub/refresh endpoint."""

    def test_refresh_without_url_returns_400(self):
        from src.server import app
        client = TestClient(app)
        resp = client.post("/arch-hub/refresh")
        assert resp.status_code == 400

    @patch("src.server.clone_arch_hub")
    def test_refresh_with_url_succeeds(self, mock_clone):
        from src import server
        from src.server import app

        # Create a temp dir with a fake arch file
        os.makedirs("/tmp/test-askbox-arch", exist_ok=True)
        with open("/tmp/test-askbox-arch/test-repo.arch.md", "w") as f:
            f.write("# Test")

        server.ARCH_HUB_PATH = "/tmp/test-askbox-arch"

        client = TestClient(app)
        resp = client.post("/arch-hub/refresh?url=https://github.com/test/hub.git")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "refreshed"
        assert data["repos"] >= 1

        # Cleanup
        server.ARCH_HUB_PATH = "/tmp/arch-hub"
        os.remove("/tmp/test-askbox-arch/test-repo.arch.md")
        os.rmdir("/tmp/test-askbox-arch")
