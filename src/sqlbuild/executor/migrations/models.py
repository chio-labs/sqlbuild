"""Model migration executor models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationArtifactNames:
    """Fresh janitor-archive names for one migration attempt's stage and displaced destination."""

    stage_name: str
    stage_qualified: str
    displaced_name: str
    displaced_qualified: str
    destination_qualified: str
    destination_exists: bool
