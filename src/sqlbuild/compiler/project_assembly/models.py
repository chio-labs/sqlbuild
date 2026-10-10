"""Resource facts the native project assembly returns, as Python's assembly builds them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
    DynamicColumnContractProof,
)
from sqlbuild.spec.contracts.models import SourceEntry


@dataclass(frozen=True, slots=True)
class NativeProjectResources:
    """Per-resource facts in input order, and whether each model's SQL passed syntax validation."""

    model_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    model_syntax_valid: tuple[bool, ...]
    source_entries: tuple[SourceEntry, ...]
    seed_destinations: tuple[CompiledRelationLocation, ...]
    function_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    audit_scope_deps: tuple[tuple[CompiledObjectKey, ...], ...]


@dataclass(frozen=True, slots=True)
class NativeModelFacts:
    """One model's native facts; each None where Python derives it."""

    deps: tuple[CompiledObjectKey, ...] | None
    dynamic_contract: DynamicColumnContractProof | None
    syntax_valid: bool = False


@dataclass(frozen=True, slots=True)
class NativeProjectFacts:
    """Every model's native facts, and the resource facts unless Python must assemble them."""

    models: tuple[NativeModelFacts, ...]
    resources: NativeProjectResources | None
