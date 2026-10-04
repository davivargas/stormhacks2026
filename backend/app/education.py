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
    EducationalPassage(
        document_id="epa-storm-drain-route",
        title="Street litter can reach waterways",
        passage=(
            "Litter left on the ground can be carried into storm drains, streams, canals, and "
            "rivers. Some storm-drain systems lead directly to larger waterways."
        ),
        source_url="https://www.epa.gov/trash-free-waters/learn-about-aquatic-trash",
        tags=("land", "storm drain", "waterways", "travel"),
    ),
    EducationalPassage(
        document_id="epa-plastic-fragments",
        title="Large plastic can become tiny pieces",
        passage=(
            "Plastic does not biodegrade like food scraps. Over time, plastic debris can weather "
            "into tiny pieces called microplastics, which are very difficult to clean up."
        ),
        source_url="https://www.epa.gov/trash-free-waters/learn-about-aquatic-trash",
        tags=("plastic", "microplastics", "breakdown", "long term"),
    ),
    EducationalPassage(
        document_id="noaa-inland-connection",
        title="Ocean protection can begin inland",
        passage=(
            "A community does not need to be beside the ocean to help prevent marine debris. "
            "Trash from streets, rivers, and streams can still become part of the ocean-waste problem."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/how-help",
        tags=("land", "rivers", "streams", "waterways", "prevention"),
    ),
    EducationalPassage(
        document_id="noaa-reusable-bottle",
        title="A reusable bottle prevents waste",
        passage=(
            "Choosing a reusable water bottle reduces the number of disposable bottles a person "
            "uses and throws away. Creating less waste means less material can become marine debris."
        ),
        source_url="https://marinedebris.noaa.gov/how-help/home",
        tags=("plastic bottle", "bottle", "reuse", "reduce", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="noaa-reusable-bag",
        title="Reusable bags replace disposable ones",
        passage=(
            "Reusable grocery bags are an everyday alternative to disposable bags. Reusing items "
            "helps reduce the amount of waste that could eventually become marine debris."
        ),
        source_url="https://marinedebris.noaa.gov/how-help/home",
        tags=("plastic bag", "bag", "reuse", "reduce", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="noaa-reusable-foodware",
        title="Reusable foodware cuts packaging waste",
        passage=(
            "Reusable cups, containers, and utensils can replace many disposable food-service "
            "items. Carrying reusables is one practical way to create less packaging waste."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/how-help",
        tags=(
            "cup",
            "container",
            "wrapper",
            "utensil",
            "food packaging",
            "reuse",
            "action",
        ),
    ),
    EducationalPassage(
        document_id="noaa-shore-pack-out",
        title="Take every beach item home",
        passage=(
            "At the shore, keeping track of containers, toys, and other belongings stops them from "
            "washing away. Trash should go in a proper bin or travel home for disposal."
        ),
        source_url="https://marinedebris.noaa.gov/how-help/shore",
        tags=("shore", "beach", "disposal", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="noaa-overflowing-bin",
        title="An overflowing bin is not secure",
        passage=(
            "Putting trash beside an overflowing bin can let it escape again. At the beach, use "
            "another proper bin or take the item home instead."
        ),
        source_url="https://marinedebris.noaa.gov/how-help/shore",
        tags=("bin", "disposal", "shore", "beach", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="noaa-safe-ordinary-cleanup",
        title="Remove ordinary litter safely",
        passage=(
            "Ordinary litter such as bottles, cans, and plastic foam can be removed and recycled "
            "when it is safe and practical. Unknown or hazardous-looking objects should not be touched."
        ),
        source_url="https://marinedebris.noaa.gov/marine-debris-handling-guidelines",
        tags=("bottle", "can", "foam", "cleanup", "safety", "captured", "action"),
    ),
    EducationalPassage(
        document_id="noaa-count-cleanup-items",
        title="Counting cleanup litter helps science",
        passage=(
            "People taking part in a community cleanup can count the types of debris they find. "
            "Monitoring litter helps communities understand what is common and where it gathers."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/how-help",
        tags=("cleanup", "monitoring", "community", "captured", "action"),
    ),
    EducationalPassage(
        document_id="noaa-current-speed-direction",
        title="Currents have speed and direction",
        passage=(
            "A current describes water in motion. Scientists measure both how fast the water "
            "moves and the direction it travels."
        ),
        source_url="https://oceanservice.noaa.gov/education/tutorial_currents/",
        tags=("ocean currents", "movement", "speed", "direction"),
    ),
    EducationalPassage(
        document_id="noaa-tidal-current-pattern",
        title="Tidal currents follow regular patterns",
        passage=(
            "The rise and fall of tides creates currents in the ocean, bays, and estuaries. "
            "Tidal currents change in regular patterns that scientists can predict."
        ),
        source_url="https://oceanservice.noaa.gov/education/tutorial_currents/",
        tags=("ocean currents", "tide", "tides", "coast", "movement"),
    ),
    EducationalPassage(
        document_id="noaa-surface-current-wind",
        title="Wind can help drive surface currents",
        passage=(
            "Winds can drive currents near the ocean surface. They can affect coastal waters on "
            "a local scale and open-ocean waters on a much larger scale."
        ),
        source_url="https://oceanservice.noaa.gov/education/tutorial_currents/",
        tags=("ocean currents", "surface", "wind", "movement"),
    ),
    EducationalPassage(
        document_id="noaa-model-distribution",
        title="Models explore where debris may gather",
        passage=(
            "Particle-tracking models help researchers explore how floating debris may spread "
            "through the ocean and where it may gather or reach shore."
        ),
        source_url=(
            "https://marinedebris.noaa.gov/modeling-and-monitoring/"
            "modeling-oceanic-transport-floating-marine-debris"
        ),
        tags=("simulation", "model", "floating", "collection", "shore"),
    ),
    EducationalPassage(
        document_id="noaa-model-possibility",
        title="A model estimates a possible path",
        passage=(
            "A particle-tracking model estimates possible movement over time rather than "
            "predicting the exact trip of one real object. Model assumptions affect the result."
        ),
        source_url=(
            "https://marinedebris.noaa.gov/modeling-and-monitoring/"
            "modeling-oceanic-transport-floating-marine-debris"
        ),
        tags=("simulation", "model", "assumptions", "uncertainty"),
    ),
    EducationalPassage(
        document_id="noaa-gyres-five-oceans",
        title="Five major ocean gyres rotate",
        passage=(
            "Five major rotating current systems, called gyres, occur across the Pacific, "
            "Atlantic, and Indian Oceans. Floating debris can collect within these systems."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/garbage-patches",
        tags=("floating", "gyres", "collection", "ocean currents"),
    ),
    EducationalPassage(
        document_id="noaa-debris-below-surface",
        title="Floating debris may be hard to see",
        passage=(
            "A garbage patch is not a solid island of trash. Debris can be widely scattered, "
            "and some floating pieces are difficult to see just below the water's surface."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris/garbage-patches",
        tags=("floating", "gyres", "surface", "collection"),
    ),
    EducationalPassage(
        document_id="noaa-microplastic-forms",
        title="Microplastics come in several forms",
        passage=(
            "Microplastics can be fragments, film, foam, fibers, pellets, or beads. They are "
            "plastic pieces smaller than about the size of a pencil eraser."
        ),
        source_url="https://marinedebris.noaa.gov/what-marine-debris/microplastics",
        tags=("plastic", "foam", "microplastics", "breakdown", "long term"),
    ),
    EducationalPassage(
        document_id="noaa-bottles-bags-fragment",
        title="Bottles and bags can form smaller plastic",
        passage=(
            "Larger plastic objects such as beverage bottles, bags, and toys can eventually form "
            "secondary microplastics as the original items break into smaller pieces."
        ),
        source_url="https://marinedebris.noaa.gov/what-marine-debris/microplastics",
        tags=(
            "plastic bottle",
            "plastic bag",
            "microplastics",
            "breakdown",
            "long term",
        ),
    ),
    EducationalPassage(
        document_id="noaa-many-debris-materials",
        title="Marine debris includes many materials",
        passage=(
            "Marine debris includes misplaced plastics, metals, rubber, paper, textiles, and "
            "fishing gear. These items do not belong in ocean or waterway environments."
        ),
        source_url="https://marinedebris.noaa.gov/discover-marine-debris",
        tags=("marine debris", "plastic", "metal", "rubber", "paper", "waterways"),
    ),
    EducationalPassage(
        document_id="epa-downstream-ocean-route",
        title="Waterways can carry litter downstream",
        passage=(
            "Poorly managed litter on land can enter a nearby waterway and travel downstream. "
            "That connected route can eventually carry trash toward the ocean."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("land", "rivers", "waterways", "travel", "ocean"),
    ),
    EducationalPassage(
        document_id="epa-secure-bin-lid",
        title="A closed bin keeps trash contained",
        passage=(
            "Closing the lid and avoiding an overfilled outdoor bin helps keep trash from "
            "escaping before collection day."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("bin", "disposal", "land", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="epa-sort-local-waste",
        title="Use local recycling and trash guidance",
        passage=(
            "Communities may have different instructions for recyclable and non-recyclable waste. "
            "Following local guidance helps put each item in the appropriate bin."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("recycle", "bin", "disposal", "community", "action"),
    ),
    EducationalPassage(
        document_id="epa-repair-reuse-items",
        title="Repairing items prevents waste",
        passage=(
            "Repairing a useful item instead of replacing it can reduce the amount of waste a "
            "person creates. Less waste means fewer items that could escape into waterways."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("repair", "reuse", "reduce", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="epa-buy-used-items",
        title="Choosing used items can reduce waste",
        passage=(
            "Buying a useful item secondhand keeps it in use for longer and can reduce the need "
            "for new packaging and waste."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("reuse", "reduce", "packaging", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="epa-cleanup-data",
        title="Cleanup counts reveal common litter",
        passage=(
            "During a local cleanup, volunteers can record the types of litter they collect. "
            "Those observations help a community learn which waste items are common."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("cleanup", "monitoring", "community", "captured", "action"),
    ),
    EducationalPassage(
        document_id="epa-share-ocean-learning",
        title="Share what you learn about litter",
        passage=(
            "Sharing what you learn with friends, family, or classmates can help more people "
            "understand how trash reaches waterways and how to prevent it."
        ),
        source_url=(
            "https://www.epa.gov/trash-free-waters/"
            "what-you-can-do-about-trash-pollution"
        ),
        tags=("education", "community", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="noaa-refuse-disposable",
        title="Refuse an unnecessary disposable item",
        passage=(
            "Politely saying no to an unnecessary disposable item prevents that item from "
            "becoming waste in the first place."
        ),
        source_url="https://marinedebris.noaa.gov/how-help/home",
        tags=("disposable", "reduce", "prevention", "action"),
    ),
    EducationalPassage(
        document_id="epa-waste-free-lunch",
        title="Pack a lunch with reusable containers",
        passage=(
            "A reusable lunch container can replace throwaway bags and wrappers. Packing only "
            "what is needed also creates less lunchtime waste."
        ),
        source_url=(
            "https://19january2021snapshot.epa.gov/trash-free-waters/"
            "ten-ways-unpackage-your-life_.html"
        ),
        tags=("bag", "wrapper", "container", "reuse", "reduce", "action"),
    ),
    EducationalPassage(
        document_id="epa-reusable-cup",
        title="Carry a reusable cup",
        passage=(
            "A reusable cup or mug can take the place of many throwaway cups, including plastic, "
            "paper, and plastic-foam cups."
        ),
        source_url=(
            "https://19january2021snapshot.epa.gov/trash-free-waters/"
            "ten-ways-unpackage-your-life_.html"
        ),
        tags=("cup", "foam", "plastic foam", "reuse", "reduce", "action"),
    ),
    EducationalPassage(
        document_id="epa-takeout-reusables",
        title="Bring reusable takeout tools",
        passage=(
            "Bringing a reusable container and utensils for food away from home can replace "
            "single-use takeout packaging."
        ),
        source_url=(
            "https://19january2021snapshot.epa.gov/trash-free-waters/"
            "ten-ways-unpackage-your-life_.html"
        ),
        tags=("container", "utensil", "packaging", "reuse", "reduce", "action"),
    ),
    EducationalPassage(
        document_id="epa-trash-capture-systems",
        title="Trash can be captured along its route",
        passage=(
            "Trash-capture systems can intercept litter at storm-drain entrances, inside pipes, "
            "at pipe outlets, or in open water. These systems need regular maintenance and emptying."
        ),
        source_url="https://www.epa.gov/trash-free-waters/learn-about-aquatic-trash",
        tags=("captured", "removal", "storm drain", "waterways", "technology"),
    ),
)

PASSAGES_BY_ID = {passage.document_id: passage for passage in EDUCATIONAL_PASSAGES}
