import pytest

from app.models import SimulationSummary, StoryDraft
from app.providers import (
    DeterministicStoryGenerator,
    GeminiStoryGenerator,
    STORY_RESPONSE_SCHEMA,
    friendly_elapsed_time,
)


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
            "possible journey. Six hours later, ocean currents carried our traveler offshore. After 18 hours, Bottle "
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
            "On Finn's map, Bottle Buddy begins a possible journey from English Bay. Six hours later, "
            "ocean currents carry our cheerful traveler offshore. After 18 hours, Bottle Buddy "
            "reaches Kitsilano Beach and settles ashore. Wind and waves stay out, and the bottle "
            "does not sink or break down. Currents can carry debris ashore, so always put plastic "
            "litter in the right bin."
        ),
    )
    with pytest.raises(ValueError, match="user's littering action"):
        GeminiStoryGenerator._validate_simulation_facts(SUMMARY, draft)


def test_live_story_rejects_raw_snake_case_identifiers() -> None:
    draft = StoryDraft(
        title="Bag Journey",
        script=(
            "When you littered the plastic_bag in English Bay, it began one possible journey. "
            "Six hours later, ocean currents carried it offshore. After 18 hours, it reached "
            "Kitsilano Beach. Wind and waves did not join in, and it did not sink or break down. "
            "Put litter safely in the right bin."
        ),
    )

    with pytest.raises(ValueError, match="snake_case"):
        GeminiStoryGenerator._validate_simulation_facts(SUMMARY, draft)


def test_live_story_rejects_decimal_measurements() -> None:
    draft = StoryDraft(
        title="Bottle Journey",
        script=(
            "When you littered the bottle in English Bay, it began one possible journey. After "
            "1.77776 hours, ocean currents carried it offshore. After 18 hours, it reached "
            "Kitsilano Beach. Wind and waves did not join in, and it did not sink or break down. "
            "Put litter safely in the right bin."
        ),
    )

    with pytest.raises(ValueError, match="decimal measurement"):
        GeminiStoryGenerator._validate_simulation_facts(SUMMARY, draft)


def test_location_context_turns_coordinates_into_route_guidance() -> None:
    summary = SimulationSummary.model_validate(
        {
            "simulation_id": "route-test",
            "litter_type": "plastic_bottle",
            "particle_id": "bottle-route",
            "duration_hours": 24,
            "events": [
                {
                    "elapsed_hours": 0,
                    "type": "released",
                    "location": "Salish Sea",
                    "coordinates": {"lon": -123.2, "lat": 48.5},
                },
                {
                    "elapsed_hours": 24,
                    "type": "still_floating",
                    "location": "Pacific Ocean",
                    "coordinates": {"lon": -124.2, "lat": 49.2},
                },
            ],
            "final_status": "floating",
            "assumptions": ["Ocean currents only"],
            "geography": {
                "start": {
                    "coordinates": {"lon": -123.2, "lat": 48.5},
                    "label": "Salish Sea",
                    "ocean": "Pacific Ocean",
                    "sea": "Salish Sea",
                    "country": "Canada",
                    "coast": "British Columbia",
                },
                "end": {
                    "coordinates": {"lon": -124.2, "lat": 49.2},
                    "label": "Pacific Ocean",
                    "ocean": "Pacific Ocean",
                },
                "traversed_regions": ["Salish Sea", "Pacific Ocean"],
            },
        }
    )

    context = GeminiStoryGenerator._build_location_context(summary)

    assert context["route_direction"] == "northwest"
    assert context["traversed_regions"] == ["Salish Sea", "Pacific Ocean"]
    assert context["event_waypoints"][0]["coordinates"] == {"lon": -123.2, "lat": 48.5}
    assert context["event_waypoints"][1]["spoken_time"] == "one day"
    assert "must not be read aloud" in context["instruction"]


def test_friendly_elapsed_time_uses_days_instead_of_hour_24() -> None:
    assert friendly_elapsed_time(6) == "six hours"
    assert friendly_elapsed_time(1.77776) == "about one hour and 45 minutes"
    assert friendly_elapsed_time(24) == "one day"
    assert friendly_elapsed_time(48) == "two days"
    assert friendly_elapsed_time(30) == "one day and six hours"
    assert friendly_elapsed_time(25.77776) == "about one day, one hour, and 45 minutes"
    assert friendly_elapsed_time(365 * 24) == "one year"


async def test_fallback_story_uses_child_friendly_elapsed_time() -> None:
    summary = SimulationSummary.model_validate(
        {
            "simulation_id": "friendly-time-test",
            "litter_type": "plastic_bag",
            "particle_id": "bag-1",
            "duration_hours": 24,
            "events": [
                {"elapsed_hours": 0, "type": "released", "location": "Salish Sea"},
                {"elapsed_hours": 24, "type": "still_floating", "location": "Pacific Ocean"},
            ],
            "final_status": "floating",
            "assumptions": ["Ocean currents only"],
        }
    )

    draft = await DeterministicStoryGenerator().generate(summary)

    assert "After one day" in draft.script
    assert "hour 24" not in draft.script.lower()
    assert "plastic bag" in draft.script.lower()
    assert "plastic_bag" not in draft.script.lower()
