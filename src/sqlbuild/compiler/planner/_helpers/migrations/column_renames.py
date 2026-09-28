"""Recognize renamed output columns only when the rest of the query is provably unchanged."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner._helpers.migrations.projections import renames_explain_change
from sqlbuild.compiler.planner.models import ColumnRenameHint, QueryProjection, QueryShape
from sqlbuild.compiler.planner.types import InputColumns


def identical_renames(
    *,
    previous: QueryShape,
    current: QueryShape,
    excluded: frozenset[str],
    declared: Mapping[str, str],
    input_columns: InputColumns,
) -> tuple[tuple[str, str], ...]:
    """Return same-expression (old, new) pairs only when renaming is the whole change."""

    removed: tuple[QueryProjection, ...]
    added: tuple[QueryProjection, ...]
    removed, added = _removed_and_added(previous=previous, current=current, excluded=excluded)
    pairs: list[tuple[str, str]] = []
    column: QueryProjection
    for column in added:
        matches: tuple[QueryProjection, ...] = tuple(
            origin for origin in removed if origin.expression == column.expression
        )
        if len(matches) != 1:
            continue
        claims: int = sum(1 for other in added if other.expression == matches[0].expression)
        if claims == 1:
            pairs.append((matches[0].name, column.name))
    if not pairs or not renames_explain_change(
        previous=previous,
        current=current,
        renames={**declared, **dict(pairs)},
        input_columns=input_columns,
    ):
        return ()
    return tuple(pairs)


def rename_hints(
    *,
    model_name: str,
    previous: QueryShape,
    current: QueryShape,
    excluded: frozenset[str],
    live_columns: frozenset[str],
) -> tuple[ColumnRenameHint, ...]:
    """Point added columns that resemble removed live columns at an explicit migrate_from."""

    removed: tuple[QueryProjection, ...]
    added: tuple[QueryProjection, ...]
    removed, added = _removed_and_added(previous=previous, current=current, excluded=excluded)
    live_removed: tuple[QueryProjection, ...] = tuple(
        origin for origin in removed if origin.key in live_columns
    )
    same_binding: bool = previous.body == current.body
    hints: list[ColumnRenameHint] = []
    column: QueryProjection
    for column in added:
        if column.key in live_columns:
            continue
        identical: tuple[str, ...] = tuple(
            origin.name
            for origin in live_removed
            if same_binding and origin.expression == column.expression
        )
        similar: tuple[str, ...] = tuple(
            origin.name
            for origin in live_removed
            if origin.references and origin.references == column.references
        )
        if identical or similar:
            hints.append(
                ColumnRenameHint(
                    model_name=model_name,
                    added_column=column.name,
                    candidate_columns=identical or similar,
                    identical=bool(identical),
                )
            )
    return tuple(hints)


def _removed_and_added(
    *, previous: QueryShape, current: QueryShape, excluded: frozenset[str]
) -> tuple[tuple[QueryProjection, ...], tuple[QueryProjection, ...]]:
    """Return previous-only and current-only output columns by case-insensitive name."""

    previous_names: frozenset[str] = frozenset(item.key for item in previous.projections)
    current_names: frozenset[str] = frozenset(item.key for item in current.projections)
    return (
        tuple(
            item
            for item in previous.projections
            if item.key not in current_names and item.key not in excluded
        ),
        tuple(
            item
            for item in current.projections
            if item.key not in previous_names and item.key not in excluded
        ),
    )
