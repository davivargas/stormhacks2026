"""FastAPI app factory. Run with: uvicorn app.main:app --reload (from backend/)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import config, db
from app.api import router as story_router
from app.cache import SQLiteCache
from app.config import Settings, get_settings
from app.providers import ElevenLabsAudioProvider, GeminiStoryGenerator
from app.retrieval import (
    GeminiEmbeddingClient,
    LocalEducationalRetriever,
    RetrievalUnavailableError,
    TiDBEducationalRetriever,
)
from app.routes import ApiError, router as simulation_router
from app.schemas import ErrorResponse
from app.services import StoryService
from app.sim import snapshot


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()  # returns False and carries on when Tiger is unreachable
    snapshot.warm_up()  # open the Copernicus dataset in the background
    yield
    db.close_pool()


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
            class UnavailableRetriever:
                mode = "tidb"

                async def retrieve(self, summary, limit=3):
                    del summary, limit
                    raise RetrievalUnavailableError("TiDB retrieval is not configured")

            retriever = UnavailableRetriever()
    else:
        retriever = LocalEducationalRetriever()

    story_generator = GeminiStoryGenerator(settings) if settings.gemini_api_key is not None else None
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
    settings: Settings | None = None,
    story_service: StoryService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    origins = list(dict.fromkeys([*config.CORS_ORIGINS, *resolved_settings.allowed_origins]))
    app = FastAPI(title="PlasticPaths API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.state.story_service = story_service or build_story_service(resolved_settings)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message, placement_id=exc.placement_id)
        return JSONResponse(status_code=exc.status, content=body.model_dump(by_alias=True, exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else first.get("msg", "invalid request")
        return JSONResponse(
            status_code=422,
            content={"code": "invalid_request", "message": message, "details": jsonable_errors(errors)},
        )

    app.include_router(simulation_router)
    app.include_router(story_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "retrieval_mode": resolved_settings.retrieval_mode}

    return app


def jsonable_errors(errors: list[dict]) -> list[dict]:
    return [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in errors]


app = create_app()
