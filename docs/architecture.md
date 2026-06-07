# Architecture

> Status: **decisions locked**. See [`decisions.md`](./decisions.md) for the
> rationale behind each choice. Implementation can begin from this document.

## Goal

A small Linux desktop tool, launched from a terminal, that lets the current
user:

1. See a list of their SLURM jobs — running now or finished in the last 7
   days — and click one.
2. See a 2-D plot of **MaxRSS per node vs absolute time**, sampled every
   3 minutes (interval is configurable in the UI).
3. See, for each visualised node, a horizontal line at that node's
   **hardware memory capacity** (`RealMemory` from `scontrol show node`).

This is a sibling tool to `dynarun-gui`. `dynarun-gui` launches and
monitors jobs; this tool visualises their memory footprint over time.

## Runtime environment

Inherited verbatim from `dynarun-gui` so the same venv, shell and SLURM
assumptions apply.

- Linux workstation accessed via DCV or VNC.
- Shell: **tcsh**. Activation via `activate.csh`.
- Python: **3.10.12** from `/home/dvilyats/bin/dyna_py_venv`.
- SLURM scheduler. All queries scoped to `$USER` (defaulting to `dvilyats`).
- `$DISPLAY` provided by DCV/VNC.

## High-level overview

```
                +--------------------------+
   tcsh user -> | scripts/launch_gui.csh   |
                +-----------+--------------+
                            |
                            v
                +--------------------------+
                |  python -m slurm_mem_gui |
                +-----------+--------------+
                            |
   +----------------------+ | +---------------------+
   |     PySide6 UI       |<+>|   Core domain       |
   |  picker + plot       |   |  (pure Python)      |
   +----------+-----------+   +----+-----+----------+
              ^                    |     |
              |   signals          |     | subprocess
              |                    v     v
   +----------+-----------+   +---------------------+
   |  QObject workers     |-->|  SLURM CLIs         |
   |  on QThreads         |   |  squeue / sacct /   |
   +----------+-----------+   |  sstat / scontrol   |
              |               +---------------------+
              v
   +----------------------+
   |  SQLite (stdlib)     |
   |  live MaxRSS samples |
   |  + node capacity     |
   +----------------------+
```

## Data sources

| Source | Used for | Notes |
| --- | --- | --- |
| `squeue -u $USER -o ...` | List running jobs | Same format string family as `dynarun-gui/core/slurm.py`. |
| `sstat -j <jobid> -P --noheader --format=JobID,NodeList,MaxRSS` | **Live time series**, every N s | Only works while the step is running. Sampled by `MemSamplerWorker`. |
| `scontrol show node <name>` | Per-node hardware memory ceiling | Parsed for `RealMemory=<MB>`. Cached once per node in SQLite. |
| `sacct -j <jobid> --format=JobID,NodeList,MaxRSS` | MaxRSS-per-node for finished jobs we never sampled | Plotted as a single flat marker; no time series. |
| Local SQLite | Persisted sampled time series | Contains only what this tool sampled live. |

> **What is *not* persisted by SLURM.** SLURM's accounting DB stores only
> per-step aggregates (`MaxRSS`). It does not store a per-sample history
> unless `acct_gather_profile/hdf5` is enabled site-wide, and we do not
> assume that. So real time-series data exists only for jobs that were
> running while this GUI was open. Past jobs we never sampled get a
> single horizontal MaxRSS marker per node — no curve. (Decision **D6**.)

## Sampling strategy

For the **currently selected running job**, a `MemSamplerWorker` calls

```
sstat -j <jobid> -P --noheader --format=JobID,NodeList,MaxRSS
```

at the user-configured interval (default **180 seconds**). Each `NodeList`
is expanded (e.g. `node[01-04]` → 4 rows), each `MaxRSS` is converted to a
canonical integer **KB** (see `core/memory_parser.py`), the row is
timestamped client-side in **UTC ISO 8601**, and written to SQLite as
`(job_id, node, ts, rss_kb)`. The plot appends one new point per node on
each tick.

The hardware ceiling for each new node seen is fetched once via
`scontrol show node <name>` → `RealMemory`, cached in SQLite
(`node_capacity` table), and drawn as a horizontal `InfiniteLine` on
that node's subplot.

If a job had multiple `srun` steps on the same node, samples are merged
into a single per-node curve by taking the per-step max at each tick
(decision **D9**).

For a **past job**: query SQLite for any stored `(node, ts, rss_kb)`. If
samples exist → plot the curve(s) and ceiling line(s) as usual. If not →
run `sacct` and plot **one horizontal MaxRSS marker per node**, plus the
`RealMemory` ceiling, with an inline note "no time series captured (job
ran before this tool was open)".

## Package layout

Matches the `dynarun-gui` `src/`-layout. Package import name
`slurm_mem_gui`, console script `slurm-mem-gui`.

```
src/slurm_mem_gui/
├── __init__.py
├── __main__.py            # entry point: `python -m slurm_mem_gui`
├── core/                  # pure-Python, no Qt imports
│   ├── config.py          # Settings dataclass: venv path, DB path, default interval (180 s)
│   ├── slurm.py           # squeue / sacct / sstat / scontrol wrappers + parsers
│   ├── memory_parser.py   # MaxRSS K/M/G → KB; NodeList expansion (node[01-04] → 4 rows)
│   └── db.py              # sqlite3 schema + DAO for samples, meta, node capacity
├── workers/               # QObject workers, moved onto QThreads
│   ├── slurm_list.py      # poll squeue + sacct -S now-7days for the picker
│   └── mem_sampler.py     # sstat every <interval> for the selected job
└── ui/
    ├── main_window.py
    ├── job_picker.py      # table: Job ID | Name | State | Start | End/Elapsed
    └── memory_plot.py     # one subplot per node, curve + RealMemory line, interval spinner
```

Scripts and docs follow `dynarun-gui`:

```
scripts/
└── launch_gui.csh         # tcsh wrapper, sources activate.csh, runs the module
docs/
├── architecture.md        # this file
└── decisions.md           # locked-in design decisions
```

## Threading model

Identical to `dynarun-gui` — same rules apply.

- The Qt event loop owns the GUI thread.
- All subprocess calls (`squeue`, `sacct`, `sstat`, `scontrol`) run on
  background `QThread`s via `QObject` workers.
- Workers communicate with the UI via Qt signals only. No shared mutable
  state.
- Each worker uses a `QTimer` to drive its own polling interval.

## Data flow

1. **Launch.** `scripts/launch_gui.csh` sources the venv and runs
   `python -m slurm_mem_gui`.
2. **Job picker.** `JobPickerDialog` opens. A `SlurmListWorker` runs once at start (and on user *Refresh*): `squeue -u dvilyats …` → running jobs only (D18). Double-click a row to select.

   No free-text Job ID entry (decision **D18**).
3. **Plot window.** On selection, `MemoryPlotWindow` opens. For each node
   observed for that job, one subplot is created (decision **D9**), laid
   out side by side (wrapped at 4 per row for jobs spanning many nodes).
   Each subplot contains:
   - Curve of `MaxRSS(t)` (KB) at absolute timestamps
     (decisions **D7**, **D12**).
   - Horizontal `InfiniteLine` at that node's `RealMemory` (KB) — the
     hardware ceiling (decision **D8**).
   - Y-axis auto-scales to include the ceiling line so headroom is
     visible at a glance.

   If the job state is *running*, a `MemSamplerWorker` is started; new
   points are appended live.
4. **Interval control.** A spinner in the plot window changes the
   sampling interval at runtime (decision **D11**). The worker's
   `QTimer` is restarted with the new value.
5. **Quit.** Workers stop, SQLite connection closes, no orphan threads.

## Plotting

**pyqtgraph** (decision **D10**).

- Native Qt widget (`PlotWidget` / `GraphicsLayoutWidget`), no extra
  event loop.
- Cheap for live updates and many points across many nodes.
- `pg.GraphicsLayoutWidget` makes the "N subplots side by side, one per
  node" layout trivial.
- `pg.InfiniteLine(angle=0, pos=real_memory_kb)` for the per-node
  hardware ceiling.
- X-axis: absolute timestamps via `pg.DateAxisItem` (decision **D12**).

Added as a pinned entry in `pyproject.toml` and installed into
`/home/dvilyats/bin/dyna_py_venv` alongside PySide6 (decision **D14**).

## SQLite schema

```sql
CREATE TABLE IF NOT EXISTS job_samples (
    job_id  TEXT    NOT NULL,
    node    TEXT    NOT NULL,
    ts      TEXT    NOT NULL,   -- ISO 8601 UTC, client clock
    rss_kb  INTEGER NOT NULL,   -- MaxRSS in kilobytes
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
    seen_at        TEXT NOT NULL
);
```

DB path: `~/.local/share/slurm-mem-gui/samples.db`
(matches `dynarun-gui/core/config.py` convention).

## Non-goals

- Replacing or reimplementing `dyrun`, `dynarun-gui`, or SLURM's own
  accounting tools.
- Showing other users' jobs (scope is `$USER` only).
- Editing jobs (no submit / cancel / requeue here — that is `dynarun-gui`).
- Reading LS-DYNA's *application-level* memory lines from `mes*` files —
  that path already exists in `lsdyna-mes-parser/slurm_parser.py` and is
  *not* the OS RSS this tool plots.
- Filling historical gaps for jobs we never sampled (decision **D6**).
