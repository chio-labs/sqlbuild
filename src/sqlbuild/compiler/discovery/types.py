"""Discovery domain types."""

from __future__ import annotations

from dataclasses import Field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, TypedDict

from sqlbuild.compiler.scopes.types import ScopeKind

if TYPE_CHECKING:
    from sqlbuild.provider.classes.provider import Provider

type ProjectProvider = Provider
type NativeLocation = tuple[str, int, int, int, int]
type NativeListing = tuple[str, list[tuple[str, bool, bool]]]
type NativeDeclarationFact = tuple[str, str, str, str, str | None, str]
type NativeFiles = list[tuple[str, tuple[object, ...]]]
type NativeFileScope = tuple[str, str, str | None, str | None, str | None]


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


class NativeScopeFields(TypedDict, total=False):
    """The scope fields of a declaration file record that native discovery listed in a role."""

    scope_kind: ScopeKind
    ownership_root: Path | None
    owning_path: Path | None
    declaration_root: Path | None


class DirectorySnapshotEntry(NamedTuple):
    """One directory entry in a discovery snapshot."""

    name: str
    is_dir: bool
    is_walkable_dir: bool
