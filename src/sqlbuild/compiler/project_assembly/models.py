"""Resource facts the native project assembly returns, as Python's assembly builds them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.spec.contracts.models import SourceEntry


@dataclass(frozen=True, slots=True)
class NativeProjectResources:
    """Per-resource facts in input order; every requested SQL string passed syntax validation."""

    model_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    source_entries: tuple[SourceEntry, ...]
    seed_destinations: tuple[CompiledRelationLocation, ...]
    function_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    audit_scope_deps: tuple[tuple[CompiledObjectKey, ...], ...]
