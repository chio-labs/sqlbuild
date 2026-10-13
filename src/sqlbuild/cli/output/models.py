"""Structured values shared by CLI output renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.cli.output.types import WrittenTargetDiagnostic


@dataclass(frozen=True)
class WrittenTarget:
    """Result of writing compiled output to target/."""

    model_count: int
    seed_count: int
    function_count: int
    audit_count: int
    test_count: int
    target_dir: Path
    diagnostics: tuple[WrittenTargetDiagnostic, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SkillInstallTarget:
    """One destination for a SQLBuild skill file."""

    name: str
    path: Path


@dataclass(frozen=True)
class SkillSettings:
    """Project skill installation preferences."""

    targets: tuple[str, ...]
    auto_update: bool
    configured: bool


@dataclass(frozen=True)
class SkillMaintenanceResult:
    """Non-blocking generated-skill maintenance result."""

    message: str = ""


@dataclass(frozen=True)
class SkillUpdateResult:
    """Result of installing or updating skill files."""

    written_paths: tuple[Path, ...]
