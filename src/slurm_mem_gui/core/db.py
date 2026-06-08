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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Commit any pending transaction and close the connection."""
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SampleDB":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SampleDB is not open — call open() first.")
        return self._conn

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
        self._db.execute(
            "INSERT OR IGNORE INTO job_samples (job_id, node, ts, rss_kb) "
            "VALUES (?, ?, ?, ?)",
            (job_id, node, ts, rss_kb),
        )
        self._db.commit()

    def get_samples(self, job_id: str) -> list[tuple[str, str, int]]:
        """Return ``[(node, ts, rss_kb), ...]`` for *job_id*, ordered by ts asc."""
        cur = self._db.execute(
            "SELECT node, ts, rss_kb FROM job_samples "
            "WHERE job_id = ? ORDER BY ts ASC",
            (job_id,),
        )
        return [(row[0], row[1], row[2]) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # node_capacity
    # ------------------------------------------------------------------

    def get_node_capacity(self, node: str) -> Optional[int]:
        """Return cached ``real_memory_kb`` for *node*, or ``None`` if not cached."""
        cur = self._db.execute(
            "SELECT real_memory_kb FROM node_capacity WHERE node = ?",
            (node,),
        )
        row = cur.fetchone()
        return row[0] if row is not None else None

    def set_node_capacity(
        self, node: str, real_memory_kb: int, seen_at: str
    ) -> None:
        """INSERT OR REPLACE node capacity entry."""
        self._db.execute(
            "INSERT OR REPLACE INTO node_capacity (node, real_memory_kb, seen_at) "
            "VALUES (?, ?, ?)",
            (node, real_memory_kb, seen_at),
        )
        self._db.commit()
