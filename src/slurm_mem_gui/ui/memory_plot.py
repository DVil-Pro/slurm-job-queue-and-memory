"""Live memory-usage plot window."""
from __future__ import annotations

from datetime import datetime, timezone

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from slurm_mem_gui.core.config import Settings
from slurm_mem_gui.core.db import SampleDB
from slurm_mem_gui.core.slurm import SstatRow, get_node_real_memory_kb


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
    A ``QSpinBox`` (range 10–3600 s) lets the user change the sampling
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Sample interval (s):"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(10, 3600)
        self._interval_spin.setValue(self._settings.default_interval_s)
        self._interval_spin.setFixedWidth(80)
        self._interval_spin.editingFinished.connect(
            lambda: self.interval_changed.emit(self._interval_spin.value())
        )
        toolbar.addWidget(self._interval_spin)
        toolbar.addStretch()
        toolbar.addWidget(QLabel(f"Job: {self._job_name}  ({self._job_id})"))
        outer.addLayout(toolbar)

        outer.addWidget(self._layout_widget)

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
        new_nodes = False

        for row in rows:
            node = row.node
            is_new = node not in self._subplots

            if is_new:
                self._get_or_create_subplot(node)
                new_nodes = True

                # Ceiling line (D8, D15)
                try:
                    ceiling_kb = self._fetch_ceiling(node)
                    ceiling_line = pg.InfiniteLine(
                        angle=0,
                        pos=ceiling_kb,
                        pen=pg.mkPen(color="r", width=1, style=Qt.PenStyle.DashLine),
                        label=f"RealMemory: {ceiling_kb // 1024} GB",
                        labelOpts={"position": 0.95, "color": "r"},
                    )
                    self._subplots[node].addItem(ceiling_line)
                except RuntimeError:
                    pass  # Non-fatal — ceiling line omitted

            # Remove placeholder on first real data point (D16)
            if node in self._placeholders:
                self._subplots[node].removeItem(self._placeholders.pop(node))

            # Accumulate and redraw curve
            ts_posix = self._ts_to_posix(row.ts)
            self._xs[node].append(ts_posix)
            self._ys[node].append(row.rss_kb)
            self._curves[node].setData(self._xs[node], self._ys[node])

        if new_nodes:
            self._rebuild_layout()

    def _get_or_create_subplot(self, node: str) -> pg.PlotItem:
        """Return the existing ``PlotItem`` for *node*, or create a new one.

        New subplots are added to ``self._subplots`` and a placeholder
        ``TextItem`` (D16) is placed inside them until real data arrives.
        Does **not** add the PlotItem to the ``GraphicsLayoutWidget``
        grid — :meth:`_rebuild_layout` handles that.
        """
        if node in self._subplots:
            return self._subplots[node]

        axis = self._make_date_axis()
        plot = pg.PlotItem(title=node, axisItems={"bottom": axis})
        plot.setLabel("left", "MaxRSS", units="KB")
        plot.showGrid(x=True, y=True, alpha=0.3)

        # Placeholder text (D16) — removed on first data point
        placeholder = pg.TextItem(
            text=self._settings.placeholder_text,
            anchor=(0.5, 0.5),
            color=(180, 180, 180),
        )
        plot.addItem(placeholder)

        # Live RSS curve
        curve = plot.plot([], [], pen=pg.mkPen(color="steelblue", width=2))

        self._subplots[node] = plot
        self._curves[node] = curve
        self._placeholders[node] = placeholder
        self._xs[node] = []
        self._ys[node] = []

        return plot

    def _fetch_ceiling(self, node: str) -> int:
        """Return ``real_memory_kb`` for *node*.

        Check ``SampleDB.get_node_capacity`` first; if not cached, call
        ``slurm.get_node_real_memory_kb`` and cache the result (D15).
        """
        cached = self._db.get_node_capacity(node)
        if cached is not None:
            return cached
        capacity_kb = get_node_real_memory_kb(node)
        seen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._db.set_node_capacity(node, capacity_kb, seen_at)
        return capacity_kb

    def _rebuild_layout(self) -> None:
        """Re-flow all subplots into the ``GraphicsLayoutWidget`` grid.

        Clears the layout and re-adds every ``PlotItem`` in insertion
        order, wrapping at ``Settings.subplot_cols`` columns (D17).

        Call after new subplots are created; avoid during live updates
        where only curve data changes.
        """
        self._layout_widget.clear()
        cols = self._settings.subplot_cols
        for i, (node, plot) in enumerate(self._subplots.items()):
            row = i // cols
            col = i % cols
            self._layout_widget.addItem(plot, row=row, col=col)

    @staticmethod
    def _make_date_axis() -> pg.DateAxisItem:
        """Return a configured ``pg.DateAxisItem`` for the X axis (D12)."""
        return pg.DateAxisItem(orientation="bottom")

    @staticmethod
    def _ts_to_posix(ts: str) -> float:
        """Convert an ISO-8601 UTC string (``YYYY-MM-DDTHH:MM:SSZ``) to POSIX float."""
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.timestamp()
