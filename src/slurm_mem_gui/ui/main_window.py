"""Application shell window."""
from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QMainWindow

from slurm_mem_gui.core.config import Settings


class MainWindow(QMainWindow):
    """Top-level application window.

    Responsibilities:

    - On :meth:`show`, immediately open :class:`~slurm_mem_gui.ui.job_picker.JobPickerDialog`.
    - When the picker emits ``job_selected``, spin up a
      :class:`~slurm_mem_gui.workers.mem_sampler.MemSamplerWorker` on a
      ``QThread`` and open :class:`~slurm_mem_gui.ui.memory_plot.MemoryPlotWindow`.
    - On ``closeEvent``, stop all worker threads cleanly (no orphan threads).
    """

    def __init__(self, settings: Settings | None = None, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings or Settings()
        self._sampler_thread: QThread | None = None

    def show(self) -> None:  # type: ignore[override]
        super().show()
        self._open_picker()

    def _open_picker(self) -> None:
        """Instantiate and exec JobPickerDialog; connect job_selected."""
        raise NotImplementedError

    def _on_job_selected(self, job_id: str, job_name: str) -> None:
        """Create MemSamplerWorker thread and open MemoryPlotWindow."""
        raise NotImplementedError

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop sampler thread before the event loop exits."""
        raise NotImplementedError
