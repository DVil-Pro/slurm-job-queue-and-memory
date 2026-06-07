"""SQLite DAO for job samples, metadata, and node-capacity cache."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS job_samples (
    job_id  TEXT    NOT NULL,
    node    TEXT    NOT NULL,
    ts      TEXT    NOT NULL,   -- ISO-8601 UTC, client clock
    rss_kb  INTEGER NOT NULL,
    PRIMARY KEY (job_id, node, ts)
);

CREATE INDEX IF NOT EXISTS idx_job_samples_job
    ON job_samples (job_id);

CREATE TABLE IF NOT EXISTS job_meta (
    job_id     TEXT PRIMARY KEY,
    name       TEXT,
    start_ts   TEXT,
    end_ts     TEXT,
    last_state TEXT
);

CREATE TABLE IF NOT EXISTS node_capacity (
    node           TEXT PRIMARY KEY,
    real_memory_kb INTEGER NOT NULL,
    seen_at        TEXT NOT NULL   -- ISO-8601 UTC
);
"""


class SampleDB:
    """SQLite data-access object.

    Manages the ``job_samples``, ``job_meta``, and ``node_capacity`` tables.

    Usage::

        db = SampleDB(Path("~/.local/share/slurm-mem-gui/samples.db").expanduser())
        with db:
            db.insert_sample(...)

    Or open/close manually::

        db.open()
        db.insert_sample(...)
        db.close()
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Create parent directories, open the SQLite connection, apply schema."""
        raise NotImplementedError

    def close(self) -> None:
        """Commit any pending transaction and close the connection."""
        raise NotImplementedError

    def __enter__(self) -> "SampleDB":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # job_samples
    # ------------------------------------------------------------------

    def insert_sample(
        self, job_id: str, node: str, ts: str, rss_kb: int
    ) -> None:
        """INSERT OR IGNORE a single sample row.

        The PRIMARY KEY ``(job_id, node, ts)`` prevents duplicates when
        the same tick is re-processed.
        """
        raise NotImplementedError

    def get_samples(self, job_id: str) -> list[tuple[str, str, int]]:
        """Return ``[(node, ts, rss_kb), ...]`` for *job_id*, ordered by ts asc."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # node_capacity
    # ------------------------------------------------------------------

    def get_node_capacity(self, node: str) -> Optional[int]:
        """Return cached ``real_memory_kb`` for *node*, or ``None`` if not cached."""
        raise NotImplementedError

    def set_node_capacity(
        self, node: str, real_memory_kb: int, seen_at: str
    ) -> None:
        """INSERT OR REPLACE node capacity entry."""
        raise NotImplementedError
