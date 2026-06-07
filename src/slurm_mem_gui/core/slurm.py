"""SLURM CLI wrappers and result dataclasses.

All functions are pure Python (no Qt).  They run subprocess calls and
return typed dataclasses.  Raise RuntimeError on non-zero exit or
unrecognised output.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class RunningJob:
    """A single entry returned by squeue."""

    job_id: str
    name: str
    state: str
    start: str   # SLURM datetime string, e.g. "2026-06-07T09:00:00"
    nodes: str   # raw NodeList string, e.g. "node[01-04]"


@dataclass
class SstatRow:
    """A single per-node MaxRSS row from sstat, client-timestamped."""

    job_id: str
    node: str
    rss_kb: int
    ts: str      # UTC ISO-8601, stamped client-side at parse time


def list_running_jobs(user: str) -> list[RunningJob]:
    """Return running jobs for *user* by calling squeue.

    Command::

        squeue -u <user> -h -t RUNNING -o '%i|%j|%T|%S|%R'

    Fields: JobID | Name | State | StartTime | NodeList.

    Returns an empty list when the user has no running jobs.
    Raises RuntimeError on non-zero squeue exit.
    """
    raise NotImplementedError


def sample_job_memory(job_id: str) -> list[SstatRow]:
    """Return per-node MaxRSS rows for *job_id* by calling sstat.

    Command::

        sstat -j <job_id> -P --noheader --format=JobID,NodeList,MaxRSS

    Each NodeList token is expanded (see memory_parser.expand_node_list).
    Multiple steps on the same node are merged by taking the per-step max
    RSS at this sample tick (D9).
    Each row is stamped with the current UTC time (ISO-8601).

    Returns an empty list when the job has no running steps (sstat
    produces no output for a pending or recently-finished job).
    Raises RuntimeError on non-zero sstat exit.
    """
    raise NotImplementedError


def get_node_real_memory_kb(node: str) -> int:
    """Return hardware memory capacity for *node* in kilobytes.

    Command::

        scontrol show node <node>

    Parses ``RealMemory=<MB>`` and multiplies by 1024 to get KB.
    scontrol access is confirmed allowed at this site (D15) — no fallback.

    Raises RuntimeError if the node is not found or the output cannot
    be parsed.
    """
    raise NotImplementedError
