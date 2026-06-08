"""Worker that polls squeue for the job picker."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from slurm_mem_gui.core.slurm import RunningJob, list_running_jobs


class SlurmListWorker(QObject):
    """Poll ``squeue`` for running jobs of the configured user.

    Designed to run on a background ``QThread``.  The picker triggers
    a poll by calling :meth:`refresh` via ``QMetaObject.invokeMethod``;
    there is no periodic timer — polls happen only on start and on
    user-initiated *Refresh* (D18: running-only scope).

    Signals
    -------
    jobs_ready : Signal(list)
        Emitted with ``list[RunningJob]`` after each successful poll.
    error : Signal(str)
        Emitted with a human-readable message on squeue failure.
    """

    jobs_ready: Signal = Signal(list)   # list[RunningJob]
    error: Signal = Signal(str)

    def __init__(self, user: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._user = user

    @Slot()
    def refresh(self) -> None:
        """Trigger a single squeue poll.

        Call from the GUI thread via::

            QMetaObject.invokeMethod(worker, "refresh", Qt.QueuedConnection)

        Emits :attr:`jobs_ready` on success or :attr:`error` on failure.
        """
        try:
            jobs: list[RunningJob] = list_running_jobs(self._user)
            self.jobs_ready.emit(jobs)
        except RuntimeError as exc:
            self.error.emit(str(exc))
