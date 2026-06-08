"""Worker that samples sstat on a timer and writes to SQLite."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from slurm_mem_gui.core.db import SampleDB
from slurm_mem_gui.core.slurm import SstatRow, get_node_real_memory_kb, sample_job_memory


class MemSamplerWorker(QObject):
    """Sample ``sstat`` for the selected job every *interval_s* seconds.

    Designed to run on a background ``QThread``.  Writes each row to
    SQLite via ``SampleDB`` and emits :attr:`new_samples` so the plot
    can update live.

    Lifecycle::

        worker = MemSamplerWorker(job_id, user, db_path, interval_s)
        worker.moveToThread(thread)
        thread.started.connect(worker.start_sampling)
        thread.start()
        # later…
        worker.stop_sampling()
        thread.quit()
        thread.wait()

    Signals
    -------
    new_samples : Signal(list)
        Emitted after each successful sample with ``list[SstatRow]``.
    error : Signal(str)
        Emitted with a human-readable message on sstat failure.
    """

    new_samples: Signal = Signal(list)   # list[SstatRow]
    error: Signal = Signal(str)

    def __init__(
        self,
        job_id: str,
        user: str,
        db_path: Path,
        interval_s: int = 180,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._user = user
        self._db_path = db_path
        self._interval_s = interval_s
        self._timer: QTimer | None = None
        self._db: SampleDB = SampleDB(db_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @Slot()
    def start_sampling(self) -> None:
        """Initialise and start the ``QTimer``.

        Must be called *after* the worker has been moved to its thread
        (``moveToThread``).  Creates the ``QTimer`` owned by this object
        so it lives on the correct thread.
        """
        self._db.open()

        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_s * 1000)
        self._timer.timeout.connect(self._do_sample)

        # Fire immediately so the plot has data without waiting one full interval
        self._do_sample()
        self._timer.start()

    @Slot()
    def stop_sampling(self) -> None:
        """Stop the ``QTimer``.

        Call before ``thread.quit()`` to avoid a pending timer callback
        running after the thread has stopped.
        """
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._db.close()

    # ------------------------------------------------------------------
    # Runtime configuration
    # ------------------------------------------------------------------

    @Slot(int)
    def set_interval(self, seconds: int) -> None:
        """Change sampling interval at runtime (D11).

        Stops and restarts the timer with the new period.  Already-
        accumulated samples are not affected.
        """
        self._interval_s = seconds
        if self._timer is not None:
            self._timer.stop()
            self._timer.setInterval(seconds * 1000)
            self._timer.start()

    # ------------------------------------------------------------------
    # Internal sample cycle
    # ------------------------------------------------------------------

    def _do_sample(self) -> None:
        """Execute one sample cycle: call sstat, persist to DB, emit signal.

        Connected to ``QTimer.timeout``.  On sstat failure emits
        :attr:`error` instead of crashing.

        For each new node seen, the hardware memory capacity is looked up
        via ``scontrol show node`` (D15) and cached in the DB
        ``node_capacity`` table so it is only fetched once per node.
        """
        try:
            rows: list[SstatRow] = sample_job_memory(self._job_id)
        except RuntimeError as exc:
            self.error.emit(str(exc))
            return

        if not rows:
            # Job has no running steps yet (pending or just finished) — skip.
            return

        for row in rows:
            self._db.insert_sample(
                job_id=row.job_id,
                node=row.node,
                ts=row.ts,
                rss_kb=row.rss_kb,
            )
            # Populate node_capacity cache if not already present (D15)
            if self._db.get_node_capacity(row.node) is None:
                try:
                    capacity_kb = get_node_real_memory_kb(row.node)
                    self._db.set_node_capacity(
                        node=row.node,
                        real_memory_kb=capacity_kb,
                        seen_at=row.ts,
                    )
                except RuntimeError as exc:
                    # Non-fatal — plot will simply omit the ceiling line
                    self.error.emit(
                        f"Could not fetch capacity for node {row.node!r}: {exc}"
                    )

        self.new_samples.emit(rows)
