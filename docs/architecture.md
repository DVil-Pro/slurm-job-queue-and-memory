# Architecture

> Status: **draft**. Reuses the conventions already locked in
> [`dynarun-gui`](https://github.com/DVil-Pro/dynarun-gui) and
> [`lsdyna-mes-parser`](https://github.com/DVil-Pro/lsdyna-mes-parser).
> Open decisions are listed at the end; nothing here is final until they are
> resolved.

## Goal

A small Linux desktop tool, launched from a terminal, that lets the current
user:

1. Pick a SLURM job — either by typing the job ID, or by selecting one from a
   list of jobs that are running now or finished in the last 7 days.
2. See a 2-D plot of **RAM used per node vs time**, sampled every 3 minutes.
3. See a horizontal "max RAM" line for each visualised node.

This is a sibling tool to `dynarun-gui`, not part of it: `dynarun-gui` is
about *launching and monitoring* jobs; this tool is about *visualising
their memory footprint over time*.

## Runtime environment (locked from sister projects)

These are not up for negotiation — they match `dynarun-gui` exactly so the
same venv, shell and SLURM assumptions apply.

- Linux workstation accessed via DCV or VNC.
- Shell: **tcsh**. Activation via `activate.csh`.
- Python: **3.10.12** from `/home/dvilyats/bin/dyna_py_venv`.
- SLURM scheduler. All queries scoped to `$USER` (defaulting to `dvilyats`).
- `$DISPLAY` is provided by DCV/VNC.

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
   |  sampled time series |
   +----------------------+
```

## Data sources

| Source                                                            | Used for                            | Notes                                              |
| ----------------------------------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| `squeue -u $USER -o ...`                                          | List running jobs                   | Same format string as `dynarun-gui/core/slurm.py`. |
| `sacct -u $USER -S now-7days --format=JobID,JobName,State,Start,End` | List past jobs (≤ 7 days)         | Default window matches `dynarun-gui`.              |
| `sstat -j <jobid> -P --noheader --format=JobID,NodeList,MaxRSS,AveRSS` | **Live time series** for a job | Only works while the step is running.              |
| `sacct -j <jobid> --format=JobID,NodeList,MaxRSS,AveRSS,Elapsed`  | Summary fallback for finished jobs  | Aggregates only — **not** a time series.           |
| Local SQLite                                                      | Persisted sampled history           | Only contains what *this tool* has sampled.        |

> **Important constraint.** SLURM's accounting database stores only
> aggregates (`MaxRSS`, `AveRSS`) per job step. It does **not** store a
> sample-by-sample RSS history (unless `acct_gather_profile/hdf5` is enabled
> site-wide, which we are not assuming). Therefore, the only way to get a
> true per-3-minute curve for a *past* job is to have sampled it ourselves
> while it was running and stored the samples locally. See "Open decisions"
> below for how this affects 7-day history.

## Sampling strategy

For the **currently selected running job**: a `MemSamplerWorker` calls

```
sstat -j <jobid> -P --noheader --format=JobID,NodeList,MaxRSS,AveRSS
```

every **180 seconds**, parses MaxRSS per node, timestamps the row in the
client (UTC), and writes `(job_id, node, ts, rss_kb)` into SQLite. The plot
window appends a point per node on each tick.

For a **past job** the plot window first queries SQLite. Two cases:

- **Samples exist** (we sampled this job while it ran): full curve.
- **No samples** (job ran on a machine where this tool was not active):
  fall back to `sacct` summary — render only the per-node MaxRSS as a
  horizontal line, with a one-line "no time series captured" note.

## Package layout (proposed)

Matches `dynarun-gui`'s `src/`-layout, package import `slurm_mem_gui`
(working name — see open decisions).

```
src/slurm_mem_gui/
├── __init__.py
├── __main__.py            # entry point: `python -m slurm_mem_gui`
├── core/                  # pure-Python, no Qt imports
│   ├── config.py          # Settings dataclass, venv path, DB path, interval
│   ├── slurm.py           # squeue / sacct / sstat / scontrol wrappers + parsers
│   ├── memory_parser.py   # RSS unit conversion (K/M/G → MB), node split-out
│   └── db.py              # sqlite3 schema + DAO for samples and job_meta
├── workers/               # QObject workers, moved onto QThreads
│   ├── slurm_list.py      # poll squeue + sacct -S now-7days for the picker
│   └── mem_sampler.py     # poll sstat every 3 min for the selected job
└── ui/                    # PySide6 widgets only
    ├── main_window.py
    ├── job_picker.py      # table of jobs + free-text "Job ID" entry
    └── memory_plot.py     # per-node curves + per-node max line
```

Scripts and docs follow `dynarun-gui`:

```
scripts/
└── launch_gui.csh         # tcsh wrapper, sources activate.csh, runs the module
docs/
├── architecture.md        # this file
├── decisions.md           # to be added once open questions are answered
└── runbook.md             # to be added
```

## Threading model

Identical to `dynarun-gui` — copy of the rules from that repo's
`docs/architecture.md`:

- The Qt event loop owns the GUI thread.
- All subprocess calls (`squeue`, `sacct`, `sstat`, `scontrol`) run on
  background `QThread`s via `QObject` workers.
- Workers communicate with the UI via Qt signals only. No shared mutable
  state.
- Each worker uses a `QTimer` to drive its own polling interval.

## Data flow

1. **Launch.** `scripts/launch_gui.csh` sources the venv and runs
   `python -m slurm_mem_gui`.
2. **Job picker.** `JobPickerDialog` opens. A `SlurmListWorker` runs
   `squeue` and `sacct -S now-7days` once at start (and on user "Refresh")
   and populates a table with columns
   `Job ID | Name | State | Start | End/Elapsed`. The dialog also exposes
   a free-text *Job ID* field for jobs not in the list.
3. **Plot window.** On selection, `MemoryPlotWindow` opens. It:
   - queries SQLite for any stored `(node, ts, rss_kb)` samples for that
     job, plots them as one curve per node;
   - for each visualised node, draws a horizontal line at that node's max
     observed RSS in the window;
   - if the job state is *running*, starts a `MemSamplerWorker` that ticks
     every 180 s and appends new points (and shifts the max line if a new
     peak is seen).
4. **Quit.** Workers stop, SQLite connection closes, no orphan threads.

## Plotting library

Working assumption: **pyqtgraph**.

- Native Qt widget (`PlotWidget`), no extra event loop.
- Cheap for live updates and for many points across many nodes.
- Auto-axes, draggable region, easy `InfiniteLine` for the per-node max.

Alternative considered: **matplotlib** via `FigureCanvasQTAgg`. Nicer
publication-quality export, but slower for live updates and pulls in a
heavier dependency. See open decision D-PLOT below.

## SQLite schema (proposed)

```sql
CREATE TABLE IF NOT EXISTS job_samples (
    job_id  TEXT    NOT NULL,
    node    TEXT    NOT NULL,
    ts      TEXT    NOT NULL,   -- ISO 8601 UTC, client clock
    rss_kb  INTEGER NOT NULL,
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
```

DB path: `~/.local/share/slurm-mem-gui/samples.db`
(same convention as `dynarun-gui/core/config.py`).

## Non-goals

- Replacing or reimplementing `dyrun`, `dynarun-gui`, or SLURM's own
  accounting tools.
- Showing other users' jobs (scope is `$USER` only).
- Editing jobs (no submit / cancel / requeue here — that's `dynarun-gui`).
- Reading LS-DYNA's *application-level* memory lines from `mes*` files —
  that path already exists in `lsdyna-mes-parser/slurm_parser.py` and is
  *not* the OS RSS this tool plots.

## Open decisions (need user input before implementation)

The architecture above is workable, but the following choices materially
change the code that gets written. Please confirm or override.

- **D-NAME — package and command name.** Working name: `slurm-mem-gui`
  (Python package `slurm_mem_gui`, console script `slurm-mem-gui`).
  The repo is `slurm-job-queue-and-memory`; should the package match
  (mouthful) or stay shorter?

- **D-HISTORY — how to populate 7-day history.**
  - Option A *(lightweight)*: only sample while the GUI is open. Past jobs
    show MaxRSS as a flat line; no time-series for them.
  - Option B *(complete)*: ship a tiny background sampler
    (`scripts/sampler.csh` as a cron entry or a `systemd --user` timer)
    that samples every 3 min for all of the user's currently-running jobs
    into the same SQLite. Then the GUI always has full history.
  - Option C: rely on SLURM HDF5 profile data
    (`acct_gather_profile/hdf5` + `sh5util`). Only viable if the cluster
    admin has enabled it.

- **D-METRIC — what does "RAM memory" mean here.** `MaxRSS` per node per
  step, `AveRSS`, or both as separate series? (`sstat` and `sacct` both
  expose both.)

- **D-GRANULARITY — one curve per node, or per `node:step`?** A job
  with multiple `srun` steps reports per step; do you want them merged
  per node or kept distinct?

- **D-MAXLINE — what does the "max RAM" horizontal line represent?**
  - (a) Peak observed RSS for that node within the visualised window.
  - (b) Node hardware capacity (`scontrol show node <name>` → `RealMemory`).
  - (c) The job's allocation (`--mem` / `--mem-per-node` / `--mem-per-cpu`).
  - (d) Multiple lines (e.g. observed peak *and* allocation).

- **D-PLOT — plotting library.** pyqtgraph (default) or matplotlib?

- **D-INTERVAL — sample interval.** Locked at 180 s, or user-configurable
  in the UI?

- **D-AXIS — X axis.** Wall-clock seconds since job start, or absolute
  timestamps (HH:MM)?

- **D-SCOPE — Job ID free entry.** When the user types a job ID that
  doesn't belong to `$USER`, do we refuse, warn, or fetch anyway?

- **D-PYQTGRAPH-DEP — third-party dependency policy.**
  `lsdyna-mes-parser` is stdlib-only; `dynarun-gui` allows PySide6.
  Adding `pyqtgraph` (or `matplotlib`) means a new entry in
  `pyproject.toml`. Acceptable, or should we install into the same
  `/home/dvilyats/bin/dyna_py_venv` and pin it there too?
