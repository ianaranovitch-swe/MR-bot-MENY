"""Работа с Postgres: тексты, фото и ссылки рубрик."""

from __future__ import annotations

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

CREATE_CONTENT_SQL = """
CREATE TABLE IF NOT EXISTS content (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""

CREATE_PHOTOS_SQL = """
CREATE TABLE IF NOT EXISTS content_photos (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL REFERENCES content(key) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    position INT NOT NULL,
    added_by BIGINT,
    added_at TIMESTAMPTZ DEFAULT now()
);
"""

CREATE_LINKS_SQL = """
CREATE TABLE IF NOT EXISTS content_links (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL REFERENCES content(key) ON DELETE CASCADE,
    url TEXT NOT NULL,
    label TEXT NOT NULL,
    position INT NOT NULL,
    added_by BIGINT,
    added_at TIMESTAMPTZ DEFAULT now()
);
"""


def load_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise ValueError(
            "Нет DATABASE_URL. На Railway добавь Postgres — переменная появится сама."
        )
    return url


async def create_pool(database_url: str | None = None) -> asyncpg.Pool:
    """Открываем набор соединений, как ящик с готовыми ручками к базе."""
    return await asyncpg.create_pool(database_url or load_database_url())


async def init_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(CREATE_CONTENT_SQL)
    await pool.execute(CREATE_PHOTOS_SQL)
    await pool.execute(CREATE_LINKS_SQL)


async def seed_content_if_empty(
    pool: asyncpg.Pool, defaults: dict[str, str]
) -> None:
    count = await pool.fetchval("SELECT COUNT(*) FROM content")
    if count:
        return
    for key, text in defaults.items():
        await pool.execute(
            """
            INSERT INTO content (key, text, updated_at)
            VALUES ($1, $2, TIMESTAMPTZ '1970-01-01+00')
            """,
            key,
            text,
        )
    logger.info("Таблица content заполнена текстами по умолчанию.")


async def fetch_content_map(pool: asyncpg.Pool) -> dict[str, str]:
    rows = await pool.fetch("SELECT key, text FROM content")
    return {str(row["key"]): str(row["text"]) for row in rows}


async def upsert_content(
    pool: asyncpg.Pool, key: str, text: str, updated_by: int
) -> None:
    await pool.execute(
        """
        INSERT INTO content (key, text, updated_by, updated_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (key) DO UPDATE
        SET text = EXCLUDED.text,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
        """,
        key,
        text,
        updated_by,
    )


async def fetch_photo_ids(pool: asyncpg.Pool, key: str) -> list[str]:
    rows = await pool.fetch(
        """
        SELECT file_id FROM content_photos
        WHERE key = $1
        ORDER BY position ASC, id ASC
        """,
        key,
    )
    return [str(row["file_id"]) for row in rows]


async def fetch_all_photo_ids(pool: asyncpg.Pool) -> dict[str, list[str]]:
    rows = await pool.fetch(
        """
        SELECT key, file_id FROM content_photos
        ORDER BY key ASC, position ASC, id ASC
        """
    )
    photos: dict[str, list[str]] = {}
    for row in rows:
        photos.setdefault(str(row["key"]), []).append(str(row["file_id"]))
    return photos


async def replace_photos(
    pool: asyncpg.Pool, key: str, file_ids: list[str], added_by: int
) -> None:
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "DELETE FROM content_photos WHERE key = $1", key
            )
            for position, file_id in enumerate(file_ids):
                await connection.execute(
                    """
                    INSERT INTO content_photos (key, file_id, position, added_by)
                    VALUES ($1, $2, $3, $4)
                    """,
                    key,
                    file_id,
                    position,
                    added_by,
                )


async def fetch_all_links(pool: asyncpg.Pool) -> dict[str, list[tuple[str, str]]]:
    rows = await pool.fetch(
        """
        SELECT key, url, label FROM content_links
        ORDER BY key ASC, position ASC, id ASC
        """
    )
    links: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        links.setdefault(str(row["key"]), []).append(
            (str(row["url"]), str(row["label"]))
        )
    return links


async def append_links(
    pool: asyncpg.Pool,
    key: str,
    items: list[tuple[str, str]],
    added_by: int,
) -> None:
    """Новые ссылки дописываем в конец. Старые не трогаем."""
    max_position = await pool.fetchval(
        "SELECT COALESCE(MAX(position), -1) FROM content_links WHERE key = $1",
        key,
    )
    start = int(max_position) if max_position is not None else -1
    async with pool.acquire() as connection:
        async with connection.transaction():
            for offset, (url, label) in enumerate(items, start=1):
                await connection.execute(
                    """
                    INSERT INTO content_links (key, url, label, position, added_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    key,
                    url,
                    label,
                    start + offset,
                    added_by,
                )


async def fetch_last_activity(pool: asyncpg.Pool) -> dict[str, object]:
    """Когда рубрику трогали в последний раз: текст, фото или ссылка."""
    """Когда рубрику трогали в последний раз: текст, фото или ссылка."""
    rows = await pool.fetch(
        """
        SELECT
            c.key,
            GREATEST(
                COALESCE(c.updated_at, TIMESTAMPTZ '1970-01-01+00'),
                COALESCE(
                    (SELECT MAX(p.added_at) FROM content_photos p WHERE p.key = c.key),
                    TIMESTAMPTZ '1970-01-01+00'
                ),
                COALESCE(
                    (SELECT MAX(l.added_at) FROM content_links l WHERE l.key = c.key),
                    TIMESTAMPTZ '1970-01-01+00'
                )
            ) AS last_at
        FROM content c
        """
    )
    return {str(row["key"]): row["last_at"] for row in rows}


def chunk_ids(items: list[str], size: int = 10) -> list[list[str]]:
    """Telegram разрешает не больше 10 фото в одной пачке."""
    return [items[index : index + size] for index in range(0, len(items), size)]
