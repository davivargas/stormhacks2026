from __future__ import annotations

from pathlib import Path

import httpx

from app.cache import SQLiteCache
from app.config import Settings
from app.main import create_app
from app.services import StoryService
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
