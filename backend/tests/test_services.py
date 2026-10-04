from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.cache import SQLiteCache
from app.config import Settings
from app.education import EDUCATIONAL_PASSAGES
from app.fixtures import BEACHED_ITEM
from app.models import FinalStatus, SimulationSummary, StoryDraft
from app.services import AudioUnavailableError, StoryService


class FakeRetriever:
    mode = "local"

    async def retrieve(self, summary: SimulationSummary, limit: int = 3):
        del summary
        return list(EDUCATIONAL_PASSAGES[:limit])


class CountingGenerator:
    def __init__(self, should_fail: bool = False):
        self.calls = 0
        self.should_fail = should_fail

    async def generate(self, summary, passages):
        del summary, passages
        self.calls += 1
        await asyncio.sleep(0.01)
        if self.should_fail:
            raise RuntimeError("provider detail that must not reach the API")
        return StoryDraft(
            title="Bottle Buddy's Current Ride",
            script=(
                "In this simulation, Bottle Buddy begins as a playful plastic bottle at hour "
                "zero. Ocean currents carry the character along the modelled path. At hour six, "
                "the bottle becomes beached, matching the supplied result. The journey lasts "
                "twenty-four hours. Wind and waves are excluded. Help protect the ocean by putting "
                "litter in the right bin."
            ),
        )


class CountingAudioProvider:
    def __init__(self, should_fail: bool = False):
        self.calls = 0
        self.should_fail = should_fail

    async def generate(self, script: str) -> bytes:
        del script
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("paid provider failed")
        return b"ID3-fake-audio"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        retrieval_mode="local",
        cache_dir=tmp_path,
        elevenlabs_voice_id="test-voice",
        elevenlabs_model_id="test-model",
    )


def make_service(
    tmp_path: Path,
    generator=None,
    audio_provider=None,
) -> StoryService:
    settings = make_settings(tmp_path)
    return StoryService(
        settings=settings,
        cache=SQLiteCache(tmp_path / "cache.sqlite3", tmp_path / "audio"),
        retriever=FakeRetriever(),
        story_generator=generator,
        audio_provider=audio_provider,
    )


@pytest.mark.parametrize("final_status", ["outside_domain", "missing_data"])
async def test_fallback_keeps_unknown_outcomes_unknown(tmp_path: Path, final_status: str) -> None:
    summary = BEACHED_ITEM.model_copy(
        update={
            "simulation_id": f"sim-{final_status}",
            "particle_id": f"particle-{final_status}",
            "final_status": FinalStatus(final_status),
        }
    )
    summary = SimulationSummary.model_validate(summary.model_dump())
    response = await make_service(tmp_path).create_story(summary)
    assert response.generation_mode == "fallback"
    assert "unknown" in response.script.lower()


async def test_story_cache_prevents_duplicate_concurrent_generation(tmp_path: Path) -> None:
    generator = CountingGenerator()
    service = make_service(tmp_path, generator=generator)
    first, second = await asyncio.gather(
        service.create_story(BEACHED_ITEM),
        service.create_story(BEACHED_ITEM),
    )
    assert generator.calls == 1
    assert first.story_id == second.story_id


async def test_provider_failure_returns_deterministic_fallback(tmp_path: Path) -> None:
    generator = CountingGenerator(should_fail=True)
    response = await make_service(tmp_path, generator=generator).create_story(BEACHED_ITEM)
    assert generator.calls == 1
    assert response.generation_mode == "fallback"
    assert response.simulation_id == BEACHED_ITEM.simulation_id
    assert "beached" in response.script.lower()


async def test_audio_failure_preserves_saved_story(tmp_path: Path) -> None:
    audio_provider = CountingAudioProvider(should_fail=True)
    service = make_service(tmp_path, audio_provider=audio_provider)
    story = await service.create_story(BEACHED_ITEM)

    with pytest.raises(AudioUnavailableError, match="captions are still available"):
        await service.create_audio(story.story_id)

    assert service.cache.get_story_by_id(story.story_id) is not None


async def test_audio_cache_avoids_repeating_paid_request(tmp_path: Path) -> None:
    audio_provider = CountingAudioProvider()
    service = make_service(tmp_path, audio_provider=audio_provider)
    story = await service.create_story(BEACHED_ITEM)
    first = await service.create_audio(story.story_id)
    second = await service.create_audio(story.story_id)

    assert audio_provider.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert first.audio_url == second.audio_url
