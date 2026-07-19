"""Warehouse metadata call-flow analysis for SQLBuild custom rules."""

from __future__ import annotations

from fensu import LocalCallEdgeFact, NamedCallFact, RuleContext

from scripts.fensu_policy.constants import (
    ATTRIBUTE_REFERENCE_KIND,
    NAME_REFERENCE_KIND,
    WAREHOUSE_METADATA_METHODS,
)


def metadata_bearing_helper_names(*, ctx: RuleContext) -> tuple[frozenset[str], frozenset[str]]:
    """Return local method and function names that transitively query metadata."""

    edges: tuple[LocalCallEdgeFact, ...] = ctx.facts.local_call_edges()
    bearing_callers: set[tuple[str, int, int]] = {
        _caller_key(edge=edge)
        for edge in edges
        if edge.callee.kind == ATTRIBUTE_REFERENCE_KIND
        and edge.callee.base_name in WAREHOUSE_METADATA_METHODS
    }
    changed: bool = True
    while changed:
        changed = False
        bearing_method_names: set[str] = {
            edge.caller.name
            for edge in edges
            if edge.caller_class is not None and _caller_key(edge=edge) in bearing_callers
        }
        bearing_function_names: set[str] = {
            edge.caller.name
            for edge in edges
            if edge.caller_class is None and _caller_key(edge=edge) in bearing_callers
        }
        for edge in edges:
            caller_key: tuple[str, int, int] = _caller_key(edge=edge)
            if caller_key in bearing_callers:
                continue
            if (
                edge.callee.kind == ATTRIBUTE_REFERENCE_KIND
                and edge.callee.base_name in bearing_method_names
            ) or (
                edge.callee.kind == NAME_REFERENCE_KIND
                and edge.callee.base_name in bearing_function_names
            ):
                bearing_callers.add(caller_key)
                changed = True

    return (
        frozenset(
            edge.caller.name
            for edge in edges
            if edge.caller_class is not None and _caller_key(edge=edge) in bearing_callers
        ),
        frozenset(
            edge.caller.name
            for edge in edges
            if edge.caller_class is None and _caller_key(edge=edge) in bearing_callers
        ),
    )


def metadata_call_label(
    *,
    call: NamedCallFact,
    bearing_method_names: frozenset[str],
    bearing_function_names: frozenset[str],
) -> str | None:
    """Return a diagnostic label when a call reaches warehouse metadata."""

    if call.reference is None:
        return None
    if call.reference.kind == ATTRIBUTE_REFERENCE_KIND:
        if call.reference.base_name in WAREHOUSE_METADATA_METHODS:
            return f".{call.reference.base_name}"
        if call.reference.base_name in bearing_method_names:
            return call.reference.base_name
        return None
    if (
        call.reference.kind == NAME_REFERENCE_KIND
        and call.reference.base_name in bearing_function_names
    ):
        return call.reference.base_name
    return None


def _caller_key(*, edge: LocalCallEdgeFact) -> tuple[str, int, int]:
    return (edge.caller.name, edge.caller.location.line, edge.caller.location.column)
