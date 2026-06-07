#!/bin/tcsh
# Launch slurm-mem-gui inside the shared virtual environment.
# Usage: ./scripts/launch_gui.csh
set VENV = /home/dvilyats/bin/dyna_py_venv
source "${VENV}/bin/activate.csh"
exec python -m slurm_mem_gui
