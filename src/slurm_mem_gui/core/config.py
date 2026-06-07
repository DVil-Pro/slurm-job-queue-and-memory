"""Application settings dataclass."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """Central configuration for slurm-mem-gui.

    All fields have sensible defaults derived from the environment or
    locked-in decisions. Pass an instance around rather than reading
    os.environ in multiple places.
    """

    user: str = field(
        default_factory=lambda: os.environ.get("USER", "dvilyats"),
    )
    db_path: Path = field(
        default_factory=lambda: (
            Path.home() / ".local" / "share" / "slurm-mem-gui" / "samples.db"
        ),
    )
    #: Default sampling interval in seconds (D11).
    default_interval_s: int = 180
    #: Maximum subplots per row in the memory plot grid (D17).
    subplot_cols: int = 4
    #: Placeholder shown before the first sample arrives (D16).
    placeholder_text: str = "Waiting for first sample …"
