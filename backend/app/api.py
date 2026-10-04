from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from .models import AudioResponse, SimulationSummary, StoryResponse
from .retrieval import RetrievalUnavailableError
from .services import AudioUnavailableError, StoryNotFoundError, StoryService


router = APIRouter(prefix="/api/stories", tags=["stories"])


def service_from(request: Request) -> StoryService:
    return request.app.state.story_service


@router.post("", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def create_story(summary: SimulationSummary, request: Request) -> StoryResponse:
    try:
        return await service_from(request).create_story(summary)
    except RetrievalUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Educational retrieval is unavailable. Verify TiDB, Gemini embedding, "
                "and seed configuration."
            ),
        ) from error


@router.post("/{story_id}/audio", response_model=AudioResponse)
async def create_audio(story_id: str, request: Request) -> AudioResponse:
    try:
        return await service_from(request).create_audio(story_id)
    except StoryNotFoundError as error:
        raise HTTPException(status_code=404, detail="Story not found") from error
    except AudioUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/{story_id}/audio/content", response_class=FileResponse)
async def serve_audio(story_id: str, request: Request) -> FileResponse:
    try:
        audio = await service_from(request).get_audio_file(story_id)
    except StoryNotFoundError as error:
        raise HTTPException(status_code=404, detail="Audio not found") from error
    return FileResponse(
        path=audio.path,
        media_type=audio.content_type,
        filename=f"{story_id}.mp3",
    )
