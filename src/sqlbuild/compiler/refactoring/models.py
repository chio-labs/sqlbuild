"""Immutable models for planned and applied project refactorings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.refactoring.types import (
    EditKind,
    RefactorOperation,
)


@dataclass(frozen=True)
class RefactorProject:
    """Compiler facts of one project, as the refactoring planner reads them."""

    project_dir: Path
    graph: ProjectGraph
    discovered: DiscoveredProjectInputs


@dataclass(frozen=True)
class RefactorRequest:
    """One requested rename or move."""

    operation: RefactorOperation
    model_name: str
    new_name: str
    column_name: str | None = None
    destination: str | None = None
    cascade: bool = False


@dataclass(frozen=True)
class TextEdit:
    """One replacement in an authored file, in offsets of the file before any edit."""

    start: int
    end: int
    replacement: str
    kind: EditKind
    line: int
    column: int
    before: str
    after: str


@dataclass(frozen=True)
class FileChange:
    """Every edit to one file, and where the file lives afterwards."""

    path: str
    original_path: str
    edits: tuple[TextEdit, ...] = field(default_factory=tuple)

    @property
    def moved(self) -> bool:
        return self.path != self.original_path


@dataclass(frozen=True)
class ManualLocation:
    """A location a refactoring cannot rewrite safely."""

    path: str
    line: int | None
    column: int | None
    reason: str


@dataclass(frozen=True)
class MigrationDeclaration:
    """A migrate_from declaration the refactoring adds to keep history."""

    model_name: str
    declaration: str
    reason: str


@dataclass(frozen=True)
class RefactorPlan:
    """Every edit, manual location, and migration of one refactoring."""

    request: RefactorRequest
    changes: tuple[FileChange, ...] = field(default_factory=tuple)
    manual: tuple[ManualLocation, ...] = field(default_factory=tuple)
    blocking: tuple[ManualLocation, ...] = field(default_factory=tuple)
    migrations: tuple[MigrationDeclaration, ...] = field(default_factory=tuple)
    renamed_columns: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    help: str | None = None
