from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .cache import SQLiteCache
from .config import Settings, get_settings
from .providers import GeminiStoryGenerator, ElevenLabsAudioProvider
from .retrieval import (
    GeminiEmbeddingClient,
    LocalEducationalRetriever,
    RetrievalUnavailableError,
    TiDBEducationalRetriever,
)
from .services import StoryService


def build_story_service(settings: Settings) -> StoryService:
    cache = SQLiteCache(
        database_path=settings.cache_dir / "stories.sqlite3",
        audio_dir=settings.cache_dir / "audio",
    )

    if settings.retrieval_mode == "tidb":
        try:
            embedder = GeminiEmbeddingClient(settings)
            retriever = TiDBEducationalRetriever(settings, embedder)
        except RetrievalUnavailableError:
            # Keep startup healthy so configuration errors are reported as a bounded 503 request.
            class UnavailableRetriever:
                mode = "tidb"

                async def retrieve(self, summary, limit=3):
                    del summary, limit
                    raise RetrievalUnavailableError("TiDB retrieval is not configured")

            retriever = UnavailableRetriever()
    else:
        retriever = LocalEducationalRetriever()

    story_generator = (
        GeminiStoryGenerator(settings) if settings.gemini_api_key is not None else None
    )
    audio_provider = (
        ElevenLabsAudioProvider(settings)
        if settings.elevenlabs_api_key is not None and settings.elevenlabs_voice_id
        else None
    )
    return StoryService(
        settings=settings,
        cache=cache,
        retriever=retriever,
        story_generator=story_generator,
        audio_provider=audio_provider,
    )


def create_app(
    settings: Settings | None = None, story_service: StoryService | None = None
) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(title="PlasticPaths Story API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.story_service = story_service or build_story_service(resolved_settings)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "retrieval_mode": resolved_settings.retrieval_mode}

    return app


app = create_app()
