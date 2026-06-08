"""Job picker dialog — shows running SLURM jobs."""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
        self.setWindowTitle("Select SLURM Job")
        self.resize(720, 400)

        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(list(self._COLUMNS))
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

        self._status_label = QLabel("Loading…")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._trigger_refresh)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        layout.addLayout(btn_row)

    def _setup_worker(self) -> None:
        """Create SlurmListWorker, move to QThread, connect signals, start thread."""
        self._worker = SlurmListWorker(self._settings.user)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.jobs_ready.connect(self._on_jobs_ready)
        self._worker.error.connect(self._on_worker_error)
        # Trigger an initial poll as soon as the thread event loop is running
        self._thread.started.connect(self._worker.refresh)
        self._thread.start()

    def _trigger_refresh(self) -> None:
        """Invoke worker.refresh() on the worker thread and show a status label."""
        self._status_label.setText("Refreshing…")
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker, "refresh", Qt.ConnectionType.QueuedConnection
            )

    def _on_jobs_ready(self, jobs: list[RunningJob]) -> None:
        """Populate the QTableWidget from the worker result list."""
        self._table.setRowCount(0)
        for job in jobs:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(job.job_id))
            self._table.setItem(row, 1, QTableWidgetItem(job.name))
            self._table.setItem(row, 2, QTableWidgetItem(job.state))
            self._table.setItem(row, 3, QTableWidgetItem(job.start))
        count = len(jobs)
        if count:
            self._table.selectRow(0)
            self._status_label.setText(f"{count} running job(s).")
        else:
            self._status_label.setText("No running jobs found.")

    def _on_worker_error(self, message: str) -> None:
        """Display error message in the status label."""
        self._status_label.setText(f"⚠ {message}")

    def _on_double_click(self, index) -> None:
        """Emit job_selected for the clicked row and accept the dialog."""
        row = index.row()
        job_id = self._table.item(row, 0).text()
        job_name = self._table.item(row, 1).text()
        self.job_selected.emit(job_id, job_name)
        self.accept()

    def _accept_selected(self) -> None:
        """Emit job_selected for the currently selected row and accept."""
        row = self._table.currentRow()
        if row < 0:
            return  # Nothing selected — do nothing
        job_id = self._table.item(row, 0).text()
        job_name = self._table.item(row, 1).text()
        self.job_selected.emit(job_id, job_name)
        self.accept()

    def _stop_worker(self) -> None:
        """Quit and wait for the worker thread."""
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def accept(self) -> None:  # type: ignore[override]
        self._stop_worker()
        super().accept()

    def reject(self) -> None:  # type: ignore[override]
        self._stop_worker()
        super().reject()
