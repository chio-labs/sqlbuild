"""Discovery domain types."""

from __future__ import annotations

from dataclasses import Field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, Protocol

from sqlbuild.compiler.scopes.types import ScopeKind


class LoaderConnectionMode(StrEnum):
    """How a source loader owns the destination warehouse connection."""

    SQLBUILD = "sqlbuild"
    EXTERNAL = "external"


class ScopedDeclarationFile(Protocol):
    """A discovered declaration file carrying the scope facts of the role that contains it."""

    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    scope_kind: ScopeKind
    ownership_root: Path | None
    owning_path: Path | None
    declaration_root: Path | None


class DirectorySnapshotEntry(NamedTuple):
    """One directory entry in a discovery snapshot."""

    name: str
    is_dir: bool
    is_walkable_dir: bool
