import pytest

from app.models import SimulationSummary, StoryDraft
from app.providers import GeminiStoryGenerator, STORY_RESPONSE_SCHEMA


def test_story_response_schema_uses_gemini_supported_keywords() -> None:
    assert STORY_RESPONSE_SCHEMA == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "script": {"type": "string"},
        },
        "required": ["title", "script"],
    }
    assert "additionalProperties" not in STORY_RESPONSE_SCHEMA


SUMMARY = SimulationSummary.model_validate(
    {
        "simulation_id": "validation-test",
        "litter_type": "plastic_bottle",
        "particle_id": "bottle-1",
        "duration_hours": 24,
        "events": [
            {"elapsed_hours": 0, "type": "released", "location": "English Bay"},
            {"elapsed_hours": 6, "type": "floating_offshore"},
            {"elapsed_hours": 18, "type": "beached", "location": "Kitsilano Beach"},
        ],
        "final_status": "beached",
        "assumptions": [
            "Ocean currents only",
            "Wind and waves are excluded",
            "The plastic does not sink or break down",
        ],
    }
)


def test_live_story_must_include_timeline_and_assumptions() -> None:
    draft = StoryDraft(
        title="Bottle Journey",
        script=(
            "On Finn's map, when you littered the bottle in English Bay, Bottle Buddy began one "
            "possible journey. By hour 6, ocean currents carried our traveler offshore. At hour 18, Bottle "
            "Buddy reaches Kitsilano Beach and settles ashore. Wind and waves stay out, and the "
            "bottle does not sink or break down. Currents can carry debris ashore, so put plastic "
            "in the right bin."
        ),
    )
    GeminiStoryGenerator._validate_simulation_facts(SUMMARY, draft)


def test_live_story_rejects_missing_release_action() -> None:
    draft = StoryDraft(
        title="Bottle Journey",
        script=(
            "On Finn's map, Bottle Buddy begins a possible journey from English Bay. By hour 6, "
            "ocean currents carry our cheerful traveler offshore. At hour 18, Bottle Buddy "
            "reaches Kitsilano Beach and settles ashore. Wind and waves stay out, and the bottle "
            "does not sink or break down. Currents can carry debris ashore, so always put plastic "
            "litter in the right bin."
        ),
    )
    with pytest.raises(ValueError, match="user's littering action"):
        GeminiStoryGenerator._validate_simulation_facts(SUMMARY, draft)
