"""Resolve cursor-input grains from captured causal evidence."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.planner.models import CursorInputRelation
from sqlbuild.microbatches.models import CausalDependencySnapshot
from sqlbuild.microbatches.types import CausalHistoryStatus


def resolve_causal_input_relations(
    *,
    relations: tuple[CursorInputRelation, ...],
    downstream_grain: str | None,
    dependencies: tuple[CausalDependencySnapshot, ...],
) -> tuple[CursorInputRelation, ...]:
    """Use declared grain when current and producer grain only for outstanding work."""

    if not dependencies or any(
        dependency.history_status == CausalHistoryStatus.UNKNOWN for dependency in dependencies
    ):
        return relations
    by_name: dict[str, CausalDependencySnapshot] = {
        dependency.producer_model_name: dependency for dependency in dependencies
    }
    resolved: list[CursorInputRelation] = []
    for relation in relations:
        dependency: CausalDependencySnapshot | None = by_name.get(
            relation.producer_model_name or ""
        )
        grain: str | None = relation.cursor_grain
        if dependency is not None:
            grain = (
                dependency.producer_cursor_grain
                if dependency.outstanding.intervals
                else downstream_grain
            )
        resolved.append(replace(relation, cursor_grain=grain))
    return tuple(resolved)
