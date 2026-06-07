"""Live memory-usage plot window."""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from slurm_mem_gui.core.config import Settings
from slurm_mem_gui.core.db import SampleDB
from slurm_mem_gui.core.slurm import SstatRow


class MemoryPlotWindow(QWidget):
    """Live MaxRSS-per-node plot for a single SLURM job.

    Layout
    ------
    ``pg.GraphicsLayoutWidget`` containing one ``PlotItem`` per node,
    wrapped at ``Settings.subplot_cols`` (4) per row (D17).

    Each subplot
    ------------
    - **Title:** node name.
    - **X axis:** absolute timestamps via ``pg.DateAxisItem`` (D12).
    - **Y axis:** MaxRSS in KB, auto-scaled to include the ceiling line.
    - **Curve:** ``pg.PlotDataItem`` updated on each
      :attr:`~slurm_mem_gui.workers.mem_sampler.MemSamplerWorker.new_samples`.
    - **Ceiling:** ``pg.InfiniteLine(angle=0, pos=real_memory_kb)`` — the
      node's hardware memory (D8, D15).
    - **Placeholder:** ``pg.TextItem`` with ``Settings.placeholder_text``
      shown until the first data point arrives (D16).

    Controls
    --------
    A ``QSpinBox`` (range 10–3600 s) lets the user change the sampling
    interval; emits :attr:`interval_changed` (D11).

    Signals
    -------
    interval_changed : Signal(int)
        Emitted when the user changes the interval spinner value.
    """

    interval_changed: Signal = Signal(int)

    def __init__(
        self,
        job_id: str,
        job_name: str,
        db: SampleDB,
        settings: Settings | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self._job_name = job_name
        self._db = db
        self._settings = settings or Settings()

        # node → PlotItem
        self._subplots: dict[str, pg.PlotItem] = {}
        # node → PlotDataItem (the live curve)
        self._curves: dict[str, pg.PlotDataItem] = {}
        # node → placeholder TextItem (removed on first sample)
        self._placeholders: dict[str, pg.TextItem] = {}
        # Accumulated data per node
        self._xs: dict[str, list[float]] = {}   # POSIX timestamps
        self._ys: dict[str, list[int]] = {}     # rss_kb values

        self._layout_widget = pg.GraphicsLayoutWidget()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the widget layout: plot area + interval spinner."""
        raise NotImplementedError

    def add_samples(self, rows: list[SstatRow]) -> None:
        """Append new samples to the plot.

        For each *node* in *rows* seen for the first time:

        1. Call :meth:`_get_or_create_subplot`.
        2. Fetch the ``RealMemory`` ceiling via :meth:`_fetch_ceiling`
           and draw an ``InfiniteLine``.
        3. Remove the placeholder ``TextItem`` if present.

        After updating all curves, call :meth:`_rebuild_layout` only
        when new subplots were created (to avoid unnecessary reflows).
        """
        raise NotImplementedError

    def _get_or_create_subplot(self, node: str) -> pg.PlotItem:
        """Return the existing ``PlotItem`` for *node*, or create a new one.

        New subplots are added to ``self._subplots`` and a placeholder
        ``TextItem`` (D16) is placed inside them until real data arrives.
        Does **not** add the PlotItem to the ``GraphicsLayoutWidget``
        grid — :meth:`_rebuild_layout` handles that.
        """
        raise NotImplementedError

    def _fetch_ceiling(self, node: str) -> int:
        """Return ``real_memory_kb`` for *node*.

        Check ``SampleDB.get_node_capacity`` first; if not cached, call
        ``slurm.get_node_real_memory_kb`` and cache the result (D15).
        """
        raise NotImplementedError

    def _rebuild_layout(self) -> None:
        """Re-flow all subplots into the ``GraphicsLayoutWidget`` grid.

        Clears the layout and re-adds every ``PlotItem`` in insertion
        order, wrapping at ``Settings.subplot_cols`` columns (D17).

        Call after new subplots are created; avoid during live updates
        where only curve data changes.
        """
        raise NotImplementedError

    @staticmethod
    def _make_date_axis() -> pg.DateAxisItem:
        """Return a configured ``pg.DateAxisItem`` for the X axis (D12)."""
        raise NotImplementedError
