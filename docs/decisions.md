# Decisions

Locked-in design decisions for `slurm-mem-gui`. Update this file whenever a
decision changes; do not silently drift in code.

D1–D4 are inherited verbatim from
[`dynarun-gui`](https://github.com/DVil-Pro/dynarun-gui/blob/main/docs/decisions.md)
because this tool runs in the same environment.

## D1 — Python runtime  *(inherited)*

- **Decision:** Python 3.10.12 from `/home/dvilyats/bin/dyna_py_venv`.
- **Why:** Same venv as `dynarun-gui`. System Python 3.6.8 is too old
  for modern typing and PySide6.
- **Implication:** `pyproject.toml` pins `requires-python = ">=3.10,<3.11"`.

## D2 — Shell for activation  *(inherited)*

- **Decision:** Launcher is **tcsh/csh** and sources `activate.csh`.
- **Why:** Interactive shell is tcsh; bash activation is not used.

## D3 — GUI toolkit  *(inherited)*

- **Decision:** **PySide6** (Qt 6).
- **Why:** Same renderer / threading story as `dynarun-gui`; same
  ergonomics over DCV/VNC.

## D4 — Storage  *(inherited pattern)*

- **Decision:** SQLite via the stdlib `sqlite3` module, file at
  `~/.local/share/slurm-mem-gui/samples.db`.
- **Why:** No extra dependency, single-file DB. Stores live samples,
  job meta, and the node-capacity cache.
- **Implication:** No ORM. Hand-written SQL in `core/db.py`.

## D5 — Tool name

- **Decision:** Package `slurm_mem_gui`, console script `slurm-mem-gui`,
  matching the working short form of the repo name.
- **Why:** User-confirmed.

## D6 — History strategy

- **Decision:** **Live-only sampling.** Only persist samples this GUI
  collects while it is open. Past jobs that were never sampled show a
  flat `MaxRSS` marker per node (from `sacct`) with no time series.
- **Why:** Avoids depending on a background cron/systemd sampler or
  cluster-side `acct_gather_profile/hdf5`. Accepted cost: no curve for
  jobs that ran while the GUI was closed.
- **Reconsider when:** A background sampler is requested explicitly, or
  the cluster admin enables HDF5 profiling.

## D7 — Memory metric

- **Decision:** Plot **MaxRSS** per node per sample. No AveRSS.
- **Why:** User-confirmed.

## D8 — Max-RAM horizontal line

- **Decision:** The horizontal line per node is the node's **hardware
  memory capacity** — `scontrol show node <name>` → `RealMemory` (MB,
  converted to KB to match the curve). One line per visualised node.
- **Why:** User-confirmed.
- **Implication:** Need `scontrol` access from the client. Cache
  results in SQLite (`node_capacity` table) so the same node is not
  re-queried each tick.

## D9 — Curve granularity

- **Decision:** **One curve per node.** A 4-node job → 4 subplots, one
  per node, drawn side by side. If a job has multiple steps on the same
  node, samples are merged into a single node-level curve by taking the
  per-step max at each sample tick.
- **Why:** User-confirmed ("if a single job had for example 4 nodes in
  use then show 4 curves next to each other").

## D10 — Plot library

- **Decision:** **pyqtgraph**.
- **Why:** Default for live Qt plots; native widget, cheap for many
  points across many subplots; trivial to draw the per-node ceiling
  with `pg.InfiniteLine` and to use absolute time via
  `pg.DateAxisItem`.
- **Implication:** New entry in `pyproject.toml`; installed into the
  shared venv (D14).

## D11 — Sample interval

- **Decision:** **Configurable in the UI**, with a default of **180 s**.
  Stored only for the current process; restart reverts to default.
- **Why:** User-confirmed.
- **Implication:** `MemSamplerWorker` exposes a slot to restart its
  `QTimer` with a new period without dropping accumulated samples.

## D12 — X axis

- **Decision:** **Absolute timestamps** (UTC client clock, displayed in
  the user's local time via `pg.DateAxisItem`).
- **Why:** User-confirmed.

## D13 — Job picker scope and entry mode

- **Decision:** The picker shows a **list only** — no free-text Job ID
  field. The list combines:
  - currently running jobs of user `dvilyats` (via `squeue`)
  - past jobs of user `dvilyats` in the last 7 days (via
    `sacct -S now-7days`)
- **Why:** User-confirmed ("show a list of currently running jobs from
  my username dvilyats"), interpreted together with the original ask
  to also include 7-day past jobs.
- **Reconsider when:** User wants to inspect another user's job, or a
  job older than 7 days.

## D14 — Third-party dependency policy

- **Decision:** It is acceptable to add `pyqtgraph` to the shared venv
  `/home/dvilyats/bin/dyna_py_venv` alongside PySide6. Pin a version
  range in `pyproject.toml`.
- **Why:** User-confirmed.
