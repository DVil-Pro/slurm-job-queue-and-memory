"""SLURM CLI wrappers and result dataclasses.

All functions are pure Python (no Qt).  They run subprocess calls and
return typed dataclasses.  Raise RuntimeError on non-zero exit or
unrecognised output.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from slurm_mem_gui.core.memory_parser import expand_node_list, parse_rss_to_kb


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
    cmd = ["squeue", "-u", user, "-h", "-t", "RUNNING", "-o", "%i|%j|%T|%S|%R"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"squeue failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc

    jobs: list[RunningJob] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        job_id, name, state, start, nodes = parts
        jobs.append(RunningJob(
            job_id=job_id.strip(),
            name=name.strip(),
            state=state.strip(),
            start=start.strip(),
            nodes=nodes.strip(),
        ))
    return jobs


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
    cmd = [
        "sstat",
        "-j", job_id,
        "-P",
        "--noheader",
        "--format=JobID,NodeList,MaxRSS",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"sstat failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Accumulate per-node maximum across all steps (D9)
    node_max: dict[str, int] = {}

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        _step_job_id, node_list_raw, rss_raw = parts

        rss_raw = rss_raw.strip()
        if not rss_raw or rss_raw == "0":
            continue
        try:
            rss_kb = parse_rss_to_kb(rss_raw)
        except ValueError:
            continue

        for node in expand_node_list(node_list_raw.strip()):
            if node not in node_max or rss_kb > node_max[node]:
                node_max[node] = rss_kb

    return [
        SstatRow(job_id=job_id, node=node, rss_kb=rss_kb, ts=ts)
        for node, rss_kb in node_max.items()
    ]


def get_node_real_memory_kb(node: str) -> int:
    """Return hardware memory capacity for *node* in kilobytes.

    Command::

        scontrol show node <node>

    Parses ``RealMemory=<MB>`` and multiplies by 1024 to get KB.
    scontrol access is confirmed allowed at this site (D15) — no fallback.

    Raises RuntimeError if the node is not found or the output cannot
    be parsed.
    """
    cmd = ["scontrol", "show", "node", node]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"scontrol failed for node {node!r} (exit {exc.returncode}): "
            f"{exc.stderr.strip()}"
        ) from exc

    m = re.search(r'\bRealMemory=(\d+)\b', result.stdout)
    if not m:
        raise RuntimeError(
            f"Could not find RealMemory in scontrol output for node {node!r}"
        )
    real_memory_mb = int(m.group(1))
    return real_memory_mb * 1024
