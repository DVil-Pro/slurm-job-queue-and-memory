"""Parsers for SLURM memory strings and NodeList expressions."""
from __future__ import annotations


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
    raise NotImplementedError


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
    raise NotImplementedError
