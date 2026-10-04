from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Sequence
from typing import Protocol

from google import genai
from google.genai import types
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, Text, create_engine, select
from tidb_vector.sqlalchemy import VectorType

from .config import Settings
from .education import EDUCATIONAL_PASSAGES, PASSAGES_BY_ID, EducationalPassage
from .models import SimulationSummary
from .retry import retry_async


ACTION_TAGS = frozenset(
    {
        "action",
        "prevention",
        "cleanup",
        "disposal",
        "reduce",
        "reuse",
        "recycle",
        "monitoring",
    }
)


class RetrievalUnavailableError(RuntimeError):
    pass


class EducationalRetriever(Protocol):
    mode: str

    async def retrieve(
        self, summary: SimulationSummary, limit: int = 3
    ) -> list[EducationalPassage]: ...


def summary_search_text(summary: SimulationSummary) -> str:
    event_types = " ".join(event.type.replace("_", " ") for event in summary.events)
    event_locations = " ".join(event.location or "" for event in summary.events)
    assumptions = " ".join(summary.assumptions)
    geography = ""
    if summary.geography is not None:
        places = [
            summary.geography.start.label,
            summary.geography.end.label,
            *(summary.geography.traversed_regions),
        ]
        if summary.geography.landfall is not None:
            places.append(summary.geography.landfall.label)
        geography = " ".join(places)
    return (
        f"{summary.litter_type.replace('_', ' ')} {event_types} {event_locations} {geography} "
        f"{summary.final_status.value.replace('_', ' ')} {assumptions}"
    )


def _is_action_passage(passage: EducationalPassage) -> bool:
    return bool(ACTION_TAGS.intersection(passage.tags))


def _item_relevance(passage: EducationalPassage, summary: SimulationSummary) -> int:
    item_tokens = set(
        re.findall(r"[a-z]+", summary.litter_type.replace("_", " ").lower())
    )
    searchable = f"{passage.title} {' '.join(passage.tags)} {passage.passage}".lower()
    return sum(token in searchable for token in item_tokens)


def _is_compatible(passage: EducationalPassage, summary: SimulationSummary) -> bool:
    assumptions = " ".join(summary.assumptions).lower()
    excludes_breakdown = (
        ("break down" in assumptions or "breakdown" in assumptions)
        and any(
            negation in assumptions
            for negation in ("does not", "do not", "no ", "excluded")
        )
    )
    if "breakdown" in passage.tags and excludes_breakdown:
        return False
    if "wind" in passage.tags and any(
        phrase in assumptions for phrase in ("no wind", "wind excluded", "wind is excluded")
    ):
        return False
    if {"tide", "tides"}.intersection(passage.tags) and "no tide" in assumptions:
        return False
    return True


def _stable_pick(
    passages: Sequence[EducationalPassage], summary: SimulationSummary, salt: str
) -> EducationalPassage | None:
    if not passages:
        return None
    key = f"{summary.simulation_id}:{summary.particle_id}:{salt}".encode()
    index = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(passages)
    return passages[index]


def select_balanced_passages(
    ranked: Sequence[EducationalPassage], summary: SimulationSummary, limit: int
) -> list[EducationalPassage]:
    """Keep vector relevance while ensuring stories get both explanation and action."""

    if limit <= 0:
        return []

    unique: list[EducationalPassage] = []
    seen_ids: set[str] = set()
    for passage in ranked:
        if passage.document_id not in seen_ids:
            seen_ids.add(passage.document_id)
            unique.append(passage)
    selected: list[EducationalPassage] = []

    outcome_tags = {
        "floating": {"floating", "movement", "travel", "gyres"},
        "beached": {"beached", "shore", "coast"},
        "captured": {"captured", "cleanup", "removal"},
        "outside_domain": {"simulation", "model", "assumptions"},
        "missing_data": {"simulation", "model", "assumptions"},
    }[summary.final_status.value]
    journey_candidates = [
        passage
        for passage in unique
        if not _is_action_passage(passage) and _is_compatible(passage, summary)
    ]
    outcome_candidates = [
        passage for passage in journey_candidates if outcome_tags.intersection(passage.tags)
    ]
    journey = _stable_pick(
        (outcome_candidates or journey_candidates)[:4], summary, "journey"
    )
    if journey is not None:
        selected.append(journey)

    if limit >= 3:
        context_candidates = [
            passage
            for passage in journey_candidates
            if passage.document_id not in {chosen.document_id for chosen in selected}
        ]
        if context_candidates:
            best_context_score = max(
                _item_relevance(passage, summary) for passage in context_candidates
            )
            best_context = [
                passage
                for passage in context_candidates
                if _item_relevance(passage, summary) == best_context_score
            ]
            context = _stable_pick(best_context[:4], summary, "context")
            if context is not None:
                selected.append(context)

    if limit >= 2:
        action_candidates = [passage for passage in unique if _is_action_passage(passage)]
        if action_candidates:
            best_action_score = max(
                _item_relevance(passage, summary) for passage in action_candidates
            )
            best_actions = [
                passage
                for passage in action_candidates
                if _item_relevance(passage, summary) == best_action_score
            ]
            action = _stable_pick(best_actions[:4], summary, "action")
            if action is not None:
                selected.append(action)

    for passage in unique:
        if len(selected) >= limit:
            break
        if passage.document_id not in {chosen.document_id for chosen in selected}:
            selected.append(passage)
    return selected[:limit]


class LocalEducationalRetriever:
    """Development-only lexical retrieval. This is deliberately not labelled as TiDB."""

    mode = "local"

    async def retrieve(
        self, summary: SimulationSummary, limit: int = 3
    ) -> list[EducationalPassage]:
        query_tokens = set(re.findall(r"[a-z]+", summary_search_text(summary).lower()))

        def score(passage: EducationalPassage) -> tuple[int, str]:
            title_and_tags = f"{passage.title} {' '.join(passage.tags)}".lower()
            body = passage.passage.lower()
            weighted = sum(3 for token in query_tokens if token in title_and_tags)
            weighted += sum(1 for token in query_tokens if token in body)
            return (-weighted, passage.document_id)

        ranked = sorted(EDUCATIONAL_PASSAGES, key=score)
        return select_balanced_passages(ranked, summary, limit)


class GeminiEmbeddingClient:
    def __init__(self, settings: Settings):
        if settings.gemini_api_key is None:
            raise RetrievalUnavailableError(
                "GEMINI_API_KEY is required for TiDB query embeddings"
            )
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.attempts = settings.provider_max_attempts
        self.client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
            http_options=types.HttpOptions(
                timeout=int(settings.provider_timeout_seconds * 1000)
            ),
        )

    async def embed(self, text: str, purpose: str) -> list[float]:
        instruction = (
            "Represent this child-friendly ocean education document for retrieval:"
            if purpose == "document"
            else "Represent this query for retrieving child-friendly ocean education facts:"
        )

        async def call() -> list[float]:
            response = await self.client.aio.models.embed_content(
                model=self.model,
                contents=f"{instruction}\n{text}",
                config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
            )
            if not response.embeddings or response.embeddings[0].values is None:
                raise RetrievalUnavailableError("embedding provider returned no vector")
            values = list(response.embeddings[0].values)
            if len(values) != self.dimensions:
                raise RetrievalUnavailableError("embedding dimensions do not match configuration")
            return values

        return await retry_async(call, self.attempts)


def make_passage_table(dimensions: int) -> Table:
    metadata = MetaData()
    return Table(
        "educational_passages",
        metadata,
        Column("document_id", String(64), primary_key=True),
        Column("title", String(255), nullable=False),
        Column("passage", Text, nullable=False),
        Column("source_url", String(1024), nullable=False),
        Column("tags", JSON, nullable=False),
        Column("embedding_model", String(128), nullable=False),
        Column("embedding_dimensions", Integer, nullable=False),
        Column("embedding", VectorType(dim=dimensions), nullable=False),
    )


class TiDBEducationalRetriever:
    mode = "tidb"

    def __init__(self, settings: Settings, embedder: GeminiEmbeddingClient):
        if settings.tidb_database_url is None:
            raise RetrievalUnavailableError(
                "TIDB_DATABASE_URL is required when RETRIEVAL_MODE=tidb"
            )
        if settings.tidb_ssl_ca is None:
            raise RetrievalUnavailableError(
                "TIDB_SSL_CA is required when RETRIEVAL_MODE=tidb"
            )
        self.embedder = embedder
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.table = make_passage_table(self.dimensions)
        self.engine = create_engine(
            settings.tidb_database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                "connect_timeout": min(10, int(settings.provider_timeout_seconds)),
                "read_timeout": int(settings.provider_timeout_seconds),
                "write_timeout": int(settings.provider_timeout_seconds),
                "ssl_ca": str(settings.tidb_ssl_ca),
                "ssl_verify_cert": True,
                "ssl_verify_identity": True,
            },
        )

    def _search(self, embedding: Sequence[float], limit: int) -> list[EducationalPassage]:
        statement = (
            select(
                self.table.c.document_id,
                self.table.c.passage,
                self.table.c.embedding_model,
                self.table.c.embedding_dimensions,
            )
            .order_by(self.table.c.embedding.cosine_distance(list(embedding)))
            .limit(limit)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()

        passages: list[EducationalPassage] = []
        for row in rows:
            if (
                row["embedding_model"] != self.model
                or row["embedding_dimensions"] != self.dimensions
            ):
                raise RetrievalUnavailableError(
                    "TiDB embeddings do not match configured model and dimensions; reseed"
                )
            canonical = PASSAGES_BY_ID.get(row["document_id"])
            if canonical is None:
                continue
            passages.append(
                EducationalPassage(
                    document_id=canonical.document_id,
                    title=canonical.title,
                    passage=row["passage"],
                    source_url=canonical.source_url,
                    tags=canonical.tags,
                )
            )
        if not passages:
            raise RetrievalUnavailableError(
                "TiDB educational collection is empty; run the seed command"
            )
        return passages

    async def retrieve(
        self, summary: SimulationSummary, limit: int = 3
    ) -> list[EducationalPassage]:
        try:
            embedding = await self.embedder.embed(summary_search_text(summary), "query")
            candidate_limit = max(limit * 8, 24)
            ranked = await asyncio.to_thread(self._search, embedding, candidate_limit)
            return select_balanced_passages(ranked, summary, limit)
        except RetrievalUnavailableError:
            raise
        except Exception as error:
            raise RetrievalUnavailableError("TiDB educational retrieval failed") from error


def serialized_vector(values: Sequence[float]) -> str:
    """Stable vector representation useful for raw SQL diagnostics."""

    return json.dumps(list(values), separators=(",", ":"))
