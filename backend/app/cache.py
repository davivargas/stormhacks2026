from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import StoryResponse


class SQLiteCache:
    """Small local hackathon cache. Provider secrets are never stored here."""

    def __init__(self, database_path: Path, audio_dir: Path):
        self.database_path = database_path
        self.audio_dir = audio_dir
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS story_cache (
                    cache_key TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL UNIQUE,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audio_cache (
                    cache_key TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    voice_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def get_story_by_key(self, cache_key: str) -> StoryResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM story_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        if row is None:
            return None
        return StoryResponse.model_validate_json(row["response_json"])

    def get_story_by_id(self, story_id: str) -> StoryResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT response_json FROM story_cache WHERE story_id = ?", (story_id,)
            ).fetchone()
        if row is None:
            return None
        return StoryResponse.model_validate_json(row["response_json"])

    def put_story(self, cache_key: str, response: StoryResponse) -> None:
        payload = response.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO story_cache (cache_key, story_id, response_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    story_id = excluded.story_id,
                    response_json = excluded.response_json
                """,
                (cache_key, response.story_id, payload),
            )

    def get_audio(self, cache_key: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM audio_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()

    def put_audio(
        self,
        cache_key: str,
        story_id: str,
        audio: bytes,
        content_type: str,
        voice_id: str,
        model_id: str,
    ) -> Path:
        destination = self.audio_dir / f"{cache_key}.mp3"
        temporary = self.audio_dir / f".{cache_key}.{os.getpid()}.tmp"
        temporary.write_bytes(audio)
        os.replace(temporary, destination)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audio_cache
                    (cache_key, story_id, file_path, content_type, voice_id, model_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    story_id = excluded.story_id,
                    file_path = excluded.file_path,
                    content_type = excluded.content_type,
                    voice_id = excluded.voice_id,
                    model_id = excluded.model_id
                """,
                (
                    cache_key,
                    story_id,
                    str(destination),
                    content_type,
                    voice_id,
                    model_id,
                ),
            )
        return destination

    @staticmethod
    def audio_path(row: sqlite3.Row) -> Path | None:
        path = Path(row["file_path"])
        return path if path.is_file() else None
