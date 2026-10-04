from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.education import EDUCATIONAL_PASSAGES
from app.models import SimulationSummary
from app import retrieval


BOTTLE_SUMMARY = SimulationSummary.model_validate(
    {
        "simulation_id": "balanced-retrieval",
        "litter_type": "plastic_bottle",
        "particle_id": "bottle-1",
        "duration_hours": 24,
        "events": [
            {"elapsed_hours": 0, "type": "released", "location": "English Bay"},
            {"elapsed_hours": 24, "type": "beached", "location": "Kitsilano Beach"},
        ],
        "final_status": "beached",
        "assumptions": [
            "Ocean currents only",
            "The plastic does not sink or break down",
        ],
    }
)


def test_tidb_engine_enforces_certificate_and_hostname_verification(
    tmp_path: Path, monkeypatch
) -> None:
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test certificate bundle")
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(retrieval, "create_engine", fake_create_engine)
    settings = Settings(
        _env_file=None,
        retrieval_mode="tidb",
        tidb_database_url="mysql+pymysql://user:encoded-password@example.com:4000/littervoyage",
        tidb_ssl_ca=ca_bundle,
    )

    retrieval.TiDBEducationalRetriever(settings, embedder=object())

    assert str(captured["url"]).startswith("mysql+pymysql://")
    connect_args = captured["connect_args"]
    assert connect_args["ssl_ca"] == str(ca_bundle)
    assert connect_args["ssl_verify_cert"] is True
    assert connect_args["ssl_verify_identity"] is True


async def test_local_retrieval_balances_journey_context_and_action() -> None:
    passages = await retrieval.LocalEducationalRetriever().retrieve(BOTTLE_SUMMARY)

    assert len(passages) == 3
    assert {"beached", "shore", "coast"}.intersection(passages[0].tags)
    assert not retrieval._is_action_passage(passages[0])
    assert retrieval._is_action_passage(passages[-1])
    action_text = (
        f"{passages[-1].title} {' '.join(passages[-1].tags)} {passages[-1].passage}"
    ).lower()
    assert "bottle" in action_text
    assert "epa-plastic-fragments" not in {passage.document_id for passage in passages}


def test_expanded_corpus_has_unique_passage_options() -> None:
    ids = [passage.document_id for passage in EDUCATIONAL_PASSAGES]

    assert len(ids) == 42
    assert len(set(ids)) == len(ids)


def test_balanced_selection_rotates_relevant_options_between_runs() -> None:
    mixes = {
        tuple(
            passage.document_id
            for passage in retrieval.select_balanced_passages(
                EDUCATIONAL_PASSAGES,
                BOTTLE_SUMMARY.model_copy(update={"simulation_id": f"run-{index}"}),
                3,
            )
        )
        for index in range(12)
    }

    assert len(mixes) >= 3


async def test_tidb_retrieval_reranks_a_broad_candidate_set(monkeypatch) -> None:
    class FakeEmbedder:
        async def embed(self, text: str, purpose: str) -> list[float]:
            assert "plastic bottle" in text
            assert purpose == "query"
            return [0.0]

    retriever = object.__new__(retrieval.TiDBEducationalRetriever)
    retriever.embedder = FakeEmbedder()
    requested_limits: list[int] = []

    def fake_search(embedding, limit):
        requested_limits.append(limit)
        return list(retrieval.EDUCATIONAL_PASSAGES)

    monkeypatch.setattr(retriever, "_search", fake_search)
    passages = await retriever.retrieve(BOTTLE_SUMMARY)

    assert requested_limits == [24]
    assert len(passages) == 3
    assert retrieval._is_action_passage(passages[-1])
