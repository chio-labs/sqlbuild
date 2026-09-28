"""Model migration executor models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import RelationGrant
from sqlbuild.compiler.compile.models import CompiledRelationLocation


@dataclass(frozen=True)
class MigrationArtifactNames:
    """Fresh janitor-archive names for one migration attempt's stage and displaced destination."""

    stage_name: str
    stage_qualified: str
    displaced_name: str
    displaced_qualified: str
    destination_qualified: str
    destination_exists: bool


@dataclass(frozen=True)
class OldNameViewSource:
    """One compatibility view to (re)create: its name, what it reads, and its column aliases."""

    old: CompiledRelationLocation
    new: CompiledRelationLocation
    column_aliases: tuple[tuple[str, str], ...]
    grants: tuple[RelationGrant, ...] = ()
