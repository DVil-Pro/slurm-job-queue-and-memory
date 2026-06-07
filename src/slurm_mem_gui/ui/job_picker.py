"""Job picker dialog — shows running SLURM jobs."""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from slurm_mem_gui.core.config import Settings
from slurm_mem_gui.core.slurm import RunningJob
from slurm_mem_gui.workers.slurm_list import SlurmListWorker


class JobPickerDialog(QDialog):
    """Modal dialog listing the user's running SLURM jobs (D18).

    Table columns: **Job ID | Name | State | Start**

    - A :class:`~slurm_mem_gui.workers.slurm_list.SlurmListWorker` is
      created and moved to a ``QThread`` during ``__init__``.
    - The worker is triggered immediately on open and on user *Refresh*.
    - Double-clicking a row, or selecting a row and pressing *OK*,
      emits :attr:`job_selected` and accepts the dialog.
    - The worker thread is stopped in :meth:`reject`/:meth:`accept`.
    """

    job_selected: Signal = Signal(str, str)  # (job_id, job_name)

    _COLUMNS = ("Job ID", "Name", "State", "Start")

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._worker: SlurmListWorker | None = None
        self._thread: QThread | None = None
        self._setup_ui()
        self._setup_worker()

    def _setup_ui(self) -> None:
        """Build the dialog layout (table, status label, buttons)."""
        raise NotImplementedError

    def _setup_worker(self) -> None:
        """Create SlurmListWorker, move to QThread, connect signals, start thread."""
        raise NotImplementedError

    def _trigger_refresh(self) -> None:
        """Invoke worker.refresh() on the worker thread and show a status label."""
        raise NotImplementedError

    def _on_jobs_ready(self, jobs: list[RunningJob]) -> None:
        """Populate the QTableWidget from the worker result list."""
        raise NotImplementedError

    def _on_worker_error(self, message: str) -> None:
        """Display error message in the status label."""
        raise NotImplementedError

    def _on_double_click(self, index) -> None:
        """Emit job_selected for the clicked row and accept the dialog."""
        raise NotImplementedError

    def _stop_worker(self) -> None:
        """Quit and wait for the worker thread."""
        raise NotImplementedError

    def accept(self) -> None:  # type: ignore[override]
        self._stop_worker()
        super().accept()

    def reject(self) -> None:  # type: ignore[override]
        self._stop_worker()
        super().reject()
