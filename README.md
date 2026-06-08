# slurm-mem-gui

Live MaxRSS-per-node memory visualiser for SLURM jobs.

Polls `sstat` on a configurable timer, persists samples to a local SQLite
database, and draws one **pyqtgraph** subplot per node — with a hardware
memory ceiling line from `scontrol show node`.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10.x (from `/home/dvilyats/bin/dyna_py_venv`) |
| PySide6 | ≥ 6.4, < 7 |
| pyqtgraph | ≥ 0.13, < 1 |
| SLURM tools | `squeue`, `sstat`, `scontrol` on `$PATH` |

> The tool shares the existing `dyna_py_venv` virtual environment used by
> `dynarun-gui`. No separate environment is needed.

---

## Installation

### 1 — Install into the shared venv (first time only)

```csh
source /home/dvilyats/bin/dyna_py_venv/bin/activate.csh
pip install pyqtgraph>=0.13,<1          # if not already present
pip install -e /path/to/slurm-mem-gui   # editable install
```

Or, after cloning the repo:

```csh
cd slurm-mem-gui
source /home/dvilyats/bin/dyna_py_venv/bin/activate.csh
pip install -e .
```

The `pyproject.toml` pins all dependencies and registers the
`slurm-mem-gui` console script automatically.

---

## Usage

### Launch via the wrapper script (recommended)

```csh
./scripts/launch_gui.csh
```

The script activates the venv and runs `python -m slurm_mem_gui`.

### Launch directly (when the venv is already active)

```csh
slurm-mem-gui
# or equivalently:
python -m slurm_mem_gui
```

---

## Workflow

1. **Job picker** opens on start — lists your currently running SLURM jobs
   (`squeue -u $USER`). Click **Refresh** to re-poll. Double-click (or
   select + OK) to open the memory plot for that job.

2. **Memory plot** opens, showing one subplot per node. Each subplot has:
   - A **live MaxRSS curve** (KB, absolute timestamps on the X axis).
   - A **red dashed ceiling line** at the node's hardware memory capacity
     (`scontrol show node` → `RealMemory`).
   - A **"Waiting for first sample…"** placeholder until the first
     `sstat` poll returns data.

3. Use the **Sample interval** spinner (top-left) to change the polling
   period at runtime (default: 180 s). The change takes effect immediately
   without losing accumulated data.

4. Samples are persisted to SQLite at
   `~/.local/share/slurm-mem-gui/samples.db` while the GUI is open.
   Closing and re-opening for the same job will not restore past curves
   (live-only sampling by design).

---

## Repository layout

```
slurm-mem-gui/
├── pyproject.toml                  # build config + dependencies
├── scripts/
│   └── launch_gui.csh              # tcsh launcher
└── src/slurm_mem_gui/
    ├── __init__.py
    ├── __main__.py                 # python -m entry point
    ├── core/
    │   ├── config.py               # Settings dataclass
    │   ├── db.py                   # SQLite DAO (SampleDB)
    │   ├── memory_parser.py        # parse_rss_to_kb, expand_node_list
    │   └── slurm.py                # squeue / sstat / scontrol wrappers
    ├── workers/
    │   ├── mem_sampler.py          # MemSamplerWorker (QTimer-driven)
    │   └── slurm_list.py           # SlurmListWorker (squeue on demand)
    └── ui/
        ├── job_picker.py           # JobPickerDialog
        ├── main_window.py          # MainWindow (app shell)
        └── memory_plot.py          # MemoryPlotWindow (live plots)
```

---

## Key design decisions

| # | Decision |
|---|----------|
| D1 | Python 3.10 from shared venv |
| D2 | tcsh/csh launcher (`activate.csh`) |
| D3 | PySide6 (Qt 6) |
| D4 | SQLite via stdlib `sqlite3`, no ORM |
| D6 | Live-only sampling — no background cron required |
| D7 | MaxRSS metric per node (no AveRSS) |
| D8 | Hardware ceiling = `RealMemory` from `scontrol show node` |
| D9 | One curve per node; multi-step jobs merged by per-tick max |
| D10 | pyqtgraph for live Qt plots |
| D11 | Configurable sample interval, default 180 s |
| D12 | Absolute UTC timestamps on X axis (`pg.DateAxisItem`) |
| D15 | `scontrol show node` is permitted at this site — no fallback |
| D16 | "Waiting for first sample …" placeholder before first data point |
| D17 | Subplot grid wraps at 4 columns |
| D18 | Job picker shows **running jobs only** (`squeue`) — no `sacct` |

Full decision log: [`docs/decisions.md`](docs/decisions.md)  
Architecture: [`docs/architecture.md`](docs/architecture.md)
