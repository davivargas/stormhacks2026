from __future__ import annotations

from pathlib import Path

import httpx

from app.cache import SQLiteCache
import app.api as story_api
from app.config import Settings
from app.main import create_app
from app.services import StoryService
from tests.test_story_summary import make_run
from tests.test_services import FakeRetriever


async def test_story_api_returns_validation_error_for_impossible_event_time(
    tmp_path: Path,
) -> None:
    settings = Settings(_env_file=None, cache_dir=tmp_path, retrieval_mode="local")
    service = StoryService(
        settings=settings,
        cache=SQLiteCache(tmp_path / "cache.sqlite3", tmp_path / "audio"),
        retriever=FakeRetriever(),
        story_generator=None,
        audio_provider=None,
    )
    transport = httpx.ASGITransport(app=create_app(settings, service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/stories",
            json={
                "simulation_id": "sim-001",
                "litter_type": "plastic_bottle",
                "particle_id": "particle-001",
                "duration_hours": 3,
                "events": [{"elapsed_hours": 4, "type": "beached"}],
                "final_status": "beached",
                "assumptions": [],
            },
        )
    assert response.status_code == 422


async def test_story_from_run_uses_backend_run_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(_env_file=None, cache_dir=tmp_path, retrieval_mode="local")
    service = StoryService(
        settings=settings,
        cache=SQLiteCache(tmp_path / "cache.sqlite3", tmp_path / "audio"),
        retriever=FakeRetriever(),
        story_generator=None,
        audio_provider=None,
    )
    monkeypatch.setattr(story_api, "get_run", lambda run_id: make_run())
    transport = httpx.ASGITransport(app=create_app(settings, service))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/run-geo-001/stories",
            json={"particle_id": "bottle-1"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["simulation_id"] == "run-geo-001"
    assert body["particle_id"] == "bottle-1"
    assert "Salish Sea" in body["script"]
