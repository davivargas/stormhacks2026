from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.dialects.mysql import insert as mysql_insert

from .config import Settings
from .education import EDUCATIONAL_PASSAGES
from .retrieval import GeminiEmbeddingClient, TiDBEducationalRetriever


async def seed(settings: Settings) -> int:
    """Idempotently upsert the curated corpus. This is never called by app startup."""

    embedder = GeminiEmbeddingClient(settings)
    repository = TiDBEducationalRetriever(settings, embedder)
    rows: list[dict[str, object]] = []
    for passage in EDUCATIONAL_PASSAGES:
        embedding = await embedder.embed(
            f"{passage.title}\n{passage.passage}\nTags: {', '.join(passage.tags)}", "document"
        )
        rows.append(
            {
                "document_id": passage.document_id,
                "title": passage.title,
                "passage": passage.passage,
                "source_url": passage.source_url,
                "tags": list(passage.tags),
                "embedding_model": settings.embedding_model,
                "embedding_dimensions": settings.embedding_dimensions,
                "embedding": embedding,
            }
        )

    def upsert() -> int:
        with repository.engine.begin() as connection:
            for row in rows:
                statement = mysql_insert(repository.table).values(**row)
                statement = statement.on_duplicate_key_update(
                    title=statement.inserted.title,
                    passage=statement.inserted.passage,
                    source_url=statement.inserted.source_url,
                    tags=statement.inserted.tags,
                    embedding_model=statement.inserted.embedding_model,
                    embedding_dimensions=statement.inserted.embedding_dimensions,
                    embedding=statement.inserted.embedding,
                )
                connection.execute(statement)
        return len(rows)

    return await asyncio.to_thread(upsert)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotently seed PlasticPaths educational passages into an existing TiDB schema."
        )
    )
    parser.parse_args()
    settings = Settings(retrieval_mode="tidb")
    count = asyncio.run(seed(settings))
    print(f"Seeded {count} educational passages into TiDB.")


if __name__ == "__main__":
    main()
