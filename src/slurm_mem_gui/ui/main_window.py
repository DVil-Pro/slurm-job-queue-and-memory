"""Application shell window."""
from __future__ import annotations

from PySide6.QtCore import QMetaObject, Qt, QThread
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
        self._sampler_worker = None
        self._plot_db = None
        self._plot_window = None
        self.setWindowTitle("slurm-mem-gui")
        self.resize(1200, 700)

    def show(self) -> None:  # type: ignore[override]
        super().show()
        self._open_picker()

    def _open_picker(self) -> None:
        """Instantiate and exec JobPickerDialog; connect job_selected."""
        from slurm_mem_gui.ui.job_picker import JobPickerDialog

        picker = JobPickerDialog(self._settings, parent=self)
        picker.job_selected.connect(self._on_job_selected)
        picker.exec()

    def _on_job_selected(self, job_id: str, job_name: str) -> None:
        """Create MemSamplerWorker thread and open MemoryPlotWindow."""
        from slurm_mem_gui.core.db import SampleDB
        from slurm_mem_gui.ui.memory_plot import MemoryPlotWindow
        from slurm_mem_gui.workers.mem_sampler import MemSamplerWorker

        # Stop any previously running sampler
        self._stop_sampler()

        # Close previous plot-window DB connection
        if self._plot_db is not None:
            self._plot_db.close()

        # Open a fresh DB connection for the plot window (read + cache access)
        self._plot_db = SampleDB(self._settings.db_path)
        self._plot_db.open()

        # Build the plot window and set it as the central widget
        plot_window = MemoryPlotWindow(
            job_id=job_id,
            job_name=job_name,
            db=self._plot_db,
            settings=self._settings,
        )
        self.setCentralWidget(plot_window)
        self.setWindowTitle(f"slurm-mem-gui — {job_name}  ({job_id})")
        self._plot_window = plot_window

        # Create sampler worker on a background thread
        worker = MemSamplerWorker(
            job_id=job_id,
            user=self._settings.user,
            db_path=self._settings.db_path,
            interval_s=self._settings.default_interval_s,
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.start_sampling)
        worker.new_samples.connect(plot_window.add_samples)
        plot_window.interval_changed.connect(worker.set_interval)

        self._sampler_worker = worker
        self._sampler_thread = thread
        thread.start()

    def _stop_sampler(self) -> None:
        """Stop the background sampler thread cleanly."""
        if self._sampler_thread is not None and self._sampler_thread.isRunning():
            if self._sampler_worker is not None:
                # Ask the worker to stop its timer and close its DB
                QMetaObject.invokeMethod(
                    self._sampler_worker,
                    "stop_sampling",
                    Qt.ConnectionType.BlockingQueuedConnection,
                )
            self._sampler_thread.quit()
            self._sampler_thread.wait()
        self._sampler_thread = None
        self._sampler_worker = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop sampler thread before the event loop exits."""
        self._stop_sampler()
        if self._plot_db is not None:
            self._plot_db.close()
            self._plot_db = None
        event.accept()
