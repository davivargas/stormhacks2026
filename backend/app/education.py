from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EducationalPassage:
    document_id: str
    title: str
    passage: str
    source_url: str
    tags: tuple[str, ...]


# Short paraphrases verified against the linked NOAA and EPA pages on 2026-10-03.
# Keep the IDs stable: story citations are resolved from this registry, never from Gemini output.
EDUCATIONAL_PASSAGES: tuple[EducationalPassage, ...] = (
    EducationalPassage(
        document_id="noaa-current-motion",
        title="What an ocean current is",
        passage=(
            "An ocean current is moving seawater. Scientists describe a current by both its "
            "speed and its direction."
        ),
        source_url="https://oceanservice.noaa.gov/education/tutorial_currents/",
        tags=("ocean currents", "movement", "direction"),
    ),
    EducationalPassage(
        document_id="noaa-current-drivers",
        title="What drives ocean currents",
        passage=(
            "Tides, winds, and differences in water density can drive ocean currents. A model "
            "may include only some of these forces, so its assumptions matter."
        ),
        source_url="https://oceanservice.noaa.gov/facts/tidescurrents.html",
        tags=("ocean currents", "tides", "wind", "density", "assumptions"),
    ),
    EducationalPassage(
        document_id="noaa-particle-models",
        title="How floating-debris models work",
        passage=(
            "Particle-tracking models estimate how drifting objects move over time. Ocean "
            "surface currents can carry simulated particles, while other models may add forces "
            "such as wind or random mixing."
        ),
        source_url=(
            "https://marinedebris.noaa.gov/modeling-and-monitoring/"
            "modeling-oceanic-transport-floating-marine-debris"
        ),
        tags=("simulation", "particle", "floating", "ocean currents", "model"),
    ),
    EducationalPassage(
        document_id="noaa-debris-moves",
        title="Floating litter does not stay put",
        passage=(
            "Some marine debris sinks, while some floats. Floating debris can move with ocean "
            "currents, so an item may travel away from where it entered the water."
        ),
        source_url="https://oceanservice.noaa.gov/news/marinedebris/ten-things.html",
        tags=("floating", "marine debris", "ocean currents", "travel"),
    ),
    EducationalPassage(
        document_id="noaa-shoreline-debris",
        title="Debris can arrive on shore",
        passage=(
            "Ocean currents can carry marine debris, and shorelines help determine where it goes. "
            "Some floating items may eventually reach the coast and become stranded there."
        ),
        source_url="https://www.noaa.gov/explainers/what-is-marine-debris",
        tags=("beached", "shore", "currents", "tides"),
    ),
    EducationalPassage(
        document_id="noaa-gyres-collect",
        title="Currents can collect debris",
        passage=(
            "Large rotating ocean-current systems called gyres can gather floating debris. The "
            "debris is spread through the water rather than forming a solid island."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/garbage-patches",
        tags=("floating", "gyres", "collection", "ocean currents"),
    ),
    EducationalPassage(
        document_id="epa-land-sources",
        title="Much aquatic trash begins on land",
        passage=(
            "Much of the trash found in rivers, lakes, estuaries, and oceans comes from sources "
            "on land. Keeping litter out of local waterways helps keep it from reaching the ocean."
        ),
        source_url="https://www.epa.gov/trash-free-waters",
        tags=("marine pollution", "land", "waterways", "prevention"),
    ),
    EducationalPassage(
        document_id="epa-reduce-reuse",
        title="Use less throwaway packaging",
        passage=(
            "Reducing the waste we create is an effective way to keep trash out of waterways. "
            "Reusable bottles, containers, and bags can replace many single-use items."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/what-you-can-do-about-trash-pollution"
        ),
        tags=("prevention", "reduce", "reuse", "action"),
    ),
    EducationalPassage(
        document_id="epa-bin-action",
        title="Put litter in the right bin",
        passage=(
            "Putting trash in the proper bin helps stop it from escaping into streets and water. "
            "If a bin is overflowing, choose another bin or take the item home."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/what-you-can-do-about-trash-pollution"
        ),
        tags=("prevention", "disposal", "bin", "action"),
    ),
    EducationalPassage(
        document_id="epa-cleanup-action",
        title="Community cleanups help",
        passage=(
            "People can help by joining a safe local waterway or beach cleanup. Removing ordinary "
            "litter before it moves again keeps that material out of the water."
        ),
        source_url="https://www.epa.gov/beaches/take-action-beach",
        tags=("cleanup", "captured", "prevention", "action"),
    ),
)

PASSAGES_BY_ID = {passage.document_id: passage for passage in EDUCATIONAL_PASSAGES}
