"""Parsers for SLURM memory strings and NodeList expressions."""
from __future__ import annotations

import re


def parse_rss_to_kb(raw: str) -> int:
    """Convert a SLURM MaxRSS string to kilobytes (integer).

    SLURM suffixes (case-insensitive):
    - ``K`` — already in kilobytes
    - ``M`` — multiply by 1 024
    - ``G`` — multiply by 1 048 576
    - bare integer — assumed kilobytes

    Examples::

        parse_rss_to_kb('512K')   # → 512
        parse_rss_to_kb('2048M')  # → 2_097_152
        parse_rss_to_kb('4G')     # → 4_194_304
        parse_rss_to_kb('1024')   # → 1024

    Raises ValueError on unrecognised format or empty string.
    """
    if not raw:
        raise ValueError("Empty RSS string")

    raw = raw.strip()
    m = re.fullmatch(r'(\d+)([KkMmGg]?)', raw)
    if not m:
        raise ValueError(f"Unrecognised MaxRSS format: {raw!r}")

    value = int(m.group(1))
    suffix = m.group(2).upper()

    if suffix in ('', 'K'):
        return value
    elif suffix == 'M':
        return value * 1_024
    elif suffix == 'G':
        return value * 1_048_576
    else:
        raise ValueError(f"Unknown suffix {suffix!r} in MaxRSS: {raw!r}")


def expand_node_list(node_list: str) -> list[str]:
    """Expand a SLURM compact NodeList to individual node names.

    Examples::

        expand_node_list('node01')           # → ['node01']
        expand_node_list('node[01-03]')      # → ['node01', 'node02', 'node03']
        expand_node_list('node[01-03,05]')   # → ['node01', 'node02', 'node03', 'node05']
        expand_node_list('a1,b2')            # → ['a1', 'b2']

    The function handles:
    - Bare names (no brackets).
    - Comma-separated lists of bare names.
    - A single bracketed range/set suffix on a common prefix.
    - Zero-padded indices (width inferred from the range string width).

    Does NOT handle multiple bracket groups on the same prefix
    (not needed for standard SLURM output).
    """
    if not node_list:
        return []

    node_list = node_list.strip()

    # Single prefix with a bracket expression, e.g. "node[01-03,05]"
    bracket_match = re.match(r'^([^\[,]+)\[([^\]]+)\]$', node_list)
    if bracket_match:
        prefix = bracket_match.group(1)
        range_str = bracket_match.group(2)
        nodes: list[str] = []
        for part in range_str.split(','):
            part = part.strip()
            if '-' in part:
                start_s, end_s = part.split('-', 1)
                width = len(start_s)  # infer zero-padding from start token
                start = int(start_s)
                end = int(end_s)
                nodes.extend(f"{prefix}{i:0{width}d}" for i in range(start, end + 1))
            else:
                # single index token
                width = len(part)
                nodes.append(f"{prefix}{int(part):0{width}d}")
        return nodes

    # No brackets — plain comma-separated bare names
    return [n.strip() for n in node_list.split(',') if n.strip()]
