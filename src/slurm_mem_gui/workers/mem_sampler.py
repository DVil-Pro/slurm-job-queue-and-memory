"""Worker that samples sstat on a timer and writes to SQLite."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from slurm_mem_gui.core.slurm import SstatRow


class MemSamplerWorker(QObject):
    """Sample ``sstat`` for the selected job every *interval_s* seconds.

    Designed to run on a background ``QThread``.  Writes each row to
    SQLite via ``SampleDB`` and emits :attr:`new_samples` so the plot
    can update live.

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

    def start_sampling(self) -> None:
        """Initialise and start the ``QTimer``.

        Must be called *after* the worker has been moved to its thread
        (``moveToThread``).  Creates the ``QTimer`` owned by this object
        so it lives on the correct thread.
        """
        raise NotImplementedError

    def stop_sampling(self) -> None:
        """Stop the ``QTimer``.

        Call before ``thread.quit()`` to avoid a pending timer callback
        running after the thread has stopped.
        """
        raise NotImplementedError

    @Slot(int)
    def set_interval(self, seconds: int) -> None:
        """Change sampling interval at runtime (D11).

        Stops and restarts the timer with the new period.  Already-
        accumulated samples are not affected.
        """
        raise NotImplementedError

    def _do_sample(self) -> None:
        """Execute one sample cycle: call sstat, persist to DB, emit signal.

        Connected to ``QTimer.timeout``.  On sstat failure emits
        :attr:`error` instead of crashing.
        """
        raise NotImplementedError
