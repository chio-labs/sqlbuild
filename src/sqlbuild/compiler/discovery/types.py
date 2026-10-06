"""Discovery domain types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import Field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol

from sqlbuild.compiler.scopes.types import ScopeKind

if TYPE_CHECKING:
    from sqlbuild.compiler.discovery.models import (
        DiscoveredDeclarationFiles,
        DiscoveredSqlModelFile,
    )
    from sqlbuild.provider.classes.provider import Provider

type ProjectProvider = Provider


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


class DeclarationFilesReuse(Protocol):
    """Reuse the non-model declaration files a previous compile parsed when only models changed."""

    def declaration_files(
        self,
        *,
        variant: str,
        discover: Callable[[], DiscoveredDeclarationFiles],
        discover_models: Callable[[], tuple[DiscoveredSqlModelFile, ...]],
    ) -> DiscoveredDeclarationFiles:
        """Return stored declaration files with freshly discovered models, or discover all."""
        ...
