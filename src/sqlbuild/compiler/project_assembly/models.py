"""Resource facts the native project assembly returns, as Python's assembly builds them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.analysis_session.types import ProofRow
from sqlbuild.compiler.project_assembly.types import NamespaceRow, ObjectKeyRow


@dataclass(frozen=True, slots=True)
class NativeProjectResources:
    """Per-resource facts in input order, and whether each model's SQL passed syntax validation."""

    model_deps: tuple[list[ObjectKeyRow], ...]
    model_syntax_valid: tuple[bool, ...]
    source_namespaces: tuple[tuple[str | None, str | None] | None, ...]
    seed_namespaces: tuple[NamespaceRow, ...]
    function_deps: tuple[list[ObjectKeyRow], ...]
    audit_scope_deps: tuple[list[ObjectKeyRow], ...]
    failure: NativeResourceFailure | None = None


@dataclass(frozen=True, slots=True)
class NativeResourceFailure:
    """The resource Python's assembly raises at, and the exception it raises there."""

    slot: str
    index: int
    error: Exception


@dataclass(frozen=True, slots=True)
class NativeModelFacts:
    """One model's native facts; its dependencies as `(resource type, name)` rows."""

    deps: list[ObjectKeyRow]
    dynamic_contract: ProofRow | None
    syntax_valid: bool = False


@dataclass(frozen=True, slots=True)
class NativeProjectFacts:
    """Every model's native facts and the resource facts."""

    models: tuple[NativeModelFacts, ...]
    resources: NativeProjectResources
