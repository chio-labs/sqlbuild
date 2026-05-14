"""Skills command models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillInstallTarget:
    """One destination for a SQLBuild skill file."""

    name: str
    path: Path


@dataclass(frozen=True)
class SkillUpdateResult:
    """Result of installing or updating skill files."""

    written_paths: tuple[Path, ...]
