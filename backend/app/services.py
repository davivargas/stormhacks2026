from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from .adapters import ContractSimulationAdapter, SimulationAdapter
from .cache import SQLiteCache
from .config import Settings
from .models import AudioResponse, SimulationSummary, StoryResponse, StorySource
from .providers import AudioProvider, DeterministicStoryGenerator, StoryGenerator
from .retrieval import EducationalRetriever


logger = logging.getLogger(__name__)


class StoryNotFoundError(LookupError):
    pass


class AudioUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioFile:
    path: Path
    content_type: str


class StoryService:
    def __init__(
        self,
        settings: Settings,
        cache: SQLiteCache,
        retriever: EducationalRetriever,
        story_generator: StoryGenerator | None,
        audio_provider: AudioProvider | None,
        simulation_adapter: SimulationAdapter | None = None,
    ):
        self.settings = settings
        self.cache = cache
        self.retriever = retriever
        self.story_generator = story_generator
        self.audio_provider = audio_provider
        self.fallback = DeterministicStoryGenerator()
        self.simulation_adapter = simulation_adapter or ContractSimulationAdapter()
        self._story_locks: dict[str, asyncio.Lock] = {}
        self._audio_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _hash(payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _story_cache_key(self, summary: SimulationSummary) -> str:
        return self._hash(
            {
                "input": summary.model_dump(mode="json"),
                "prompt_version": self.settings.story_prompt_version,
                "retrieval_version": self.settings.retrieval_version,
                "retrieval_mode": self.retriever.mode,
                "gemini_model": self.settings.gemini_model,
            }
        )

    def _audio_cache_key(self, story: StoryResponse) -> str:
        return self._hash(
            {
                "script": story.script,
                "voice_id": self.settings.elevenlabs_voice_id,
                "model_id": self.settings.elevenlabs_model_id,
                "output_format": self.settings.elevenlabs_output_format,
            }
        )

    async def create_story(self, payload: SimulationSummary) -> StoryResponse:
        summary = self.simulation_adapter.normalize(payload)
        cache_key = self._story_cache_key(summary)
        cached = await asyncio.to_thread(self.cache.get_story_by_key, cache_key)
        if cached is not None:
            return cached

        lock = self._story_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = await asyncio.to_thread(self.cache.get_story_by_key, cache_key)
            if cached is not None:
                return cached

            passages = await self.retriever.retrieve(summary)
            generation_mode = "live"
            if self.story_generator is None:
                draft = await self.fallback.generate(summary)
                generation_mode = "fallback"
            else:
                try:
                    draft = await self.story_generator.generate(summary, passages)
                except Exception:
                    logger.warning("Gemini story generation failed; using deterministic fallback")
                    draft = await self.fallback.generate(summary)
                    generation_mode = "fallback"

            response = StoryResponse(
                story_id=f"story-{uuid.uuid4()}",
                simulation_id=summary.simulation_id,
                particle_id=summary.particle_id,
                title=draft.title,
                script=draft.script,
                sources=[
                    StorySource(
                        document_id=passage.document_id,
                        title=passage.title,
                        url=passage.source_url,
                    )
                    for passage in passages
                ],
                generation_mode=generation_mode,
                retrieval_mode=self.retriever.mode,
            )
            await asyncio.to_thread(self.cache.put_story, cache_key, response)
            return response

    async def create_audio(self, story_id: str) -> AudioResponse:
        story = await asyncio.to_thread(self.cache.get_story_by_id, story_id)
        if story is None:
            raise StoryNotFoundError(story_id)
        cache_key = self._audio_cache_key(story)
        cached = await asyncio.to_thread(self.cache.get_audio, cache_key)
        if cached is not None and self.cache.audio_path(cached) is not None:
            return self._audio_response(story, cached["content_type"], cached=True)

        if self.audio_provider is None:
            raise AudioUnavailableError(
                "Narration is unavailable until ElevenLabs credentials and a voice are configured."
            )

        lock = self._audio_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = await asyncio.to_thread(self.cache.get_audio, cache_key)
            if cached is not None and self.cache.audio_path(cached) is not None:
                return self._audio_response(story, cached["content_type"], cached=True)
            try:
                audio = await self.audio_provider.generate(story.script)
            except Exception as error:
                logger.warning("ElevenLabs narration failed; story remains available")
                raise AudioUnavailableError(
                    "Narration could not be generated. The story and captions are still available."
                ) from error
            content_type = "audio/mpeg"
            await asyncio.to_thread(
                self.cache.put_audio,
                cache_key,
                story.story_id,
                audio,
                content_type,
                self.settings.elevenlabs_voice_id,
                self.settings.elevenlabs_model_id,
            )
            return self._audio_response(story, content_type, cached=False)

    def _audio_response(
        self, story: StoryResponse, content_type: str, cached: bool
    ) -> AudioResponse:
        return AudioResponse(
            story_id=story.story_id,
            audio_url=f"/api/stories/{story.story_id}/audio/content",
            content_type=content_type,
            script=story.script,
            voice_id=self.settings.elevenlabs_voice_id,
            model_id=self.settings.elevenlabs_model_id,
            cached=cached,
        )

    async def get_audio_file(self, story_id: str) -> AudioFile:
        story = await asyncio.to_thread(self.cache.get_story_by_id, story_id)
        if story is None:
            raise StoryNotFoundError(story_id)
        row = await asyncio.to_thread(self.cache.get_audio, self._audio_cache_key(story))
        if row is None:
            raise StoryNotFoundError("audio has not been generated")
        path = self.cache.audio_path(row)
        if path is None:
            raise StoryNotFoundError("cached audio file is missing")
        return AudioFile(path=path, content_type=row["content_type"])
