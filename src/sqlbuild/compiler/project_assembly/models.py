"""Resource facts the native project assembly returns, as Python's assembly builds them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NativeProjectResources:
    """Per-resource facts in input order, and whether each model's SQL passed syntax validation."""

    model_deps: tuple[list[tuple[str, str]], ...]
    model_syntax_valid: tuple[bool, ...]
    source_namespaces: tuple[tuple[str | None, str | None] | None, ...]
    seed_namespaces: tuple[tuple[str | None, str | None, str | None, str | None], ...]
    function_deps: tuple[list[tuple[str, str]], ...]
    audit_scope_deps: tuple[list[tuple[str, str]], ...]
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

    deps: list[tuple[str, str]]
    dynamic_contract: (
        tuple[
            bool,
            list[tuple[str, str | None, str]],
            list[tuple[str, str | None]],
            list[str],
            str | None,
            bool,
        ]
        | None
    )
    syntax_valid: bool = False


@dataclass(frozen=True, slots=True)
class NativeProjectFacts:
    """Every model's native facts and the resource facts."""

    models: tuple[NativeModelFacts, ...]
    resources: NativeProjectResources
