"""Immutable models for planned and applied project refactorings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph


@dataclass(frozen=True)
class RefactorProject:
    """Compiler facts of one project, as the refactoring planner reads them."""

    project_dir: Path
    graph: ProjectGraph
    discovered: DiscoveredProjectInputs


@dataclass(frozen=True)
class ManualLocation:
    """A location a refactoring cannot rewrite safely."""

    path: str
    line: int | None
    column: int | None
    reason: str
