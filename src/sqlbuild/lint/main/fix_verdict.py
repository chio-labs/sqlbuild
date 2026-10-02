"""Attribute compile differences between a baseline and a fixed project to edited files."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.lint.constants import (
    FIX_COLUMNS_CHANGED,
    FIX_COLUMNS_UNKNOWN,
    FIX_DEPENDENCIES_CHANGED,
    FIX_LINEAGE_CHANGED,
    FIX_NEW_DIAGNOSTICS,
)
from sqlbuild.lint.models import CompileFacts, FixVerdict
from sqlbuild.lint.types import DiagnosticIdentity


def fix_verdict(
    *, before: CompileFacts, after: CompileFacts, edited: frozenset[Path]
) -> FixVerdict:
    """Edited files may lose diagnostics but not gain any; everything else must not change."""

    if set(before.models) != set(after.models):
        return FixVerdict(failing={}, unattributed=True)
    failing: dict[Path, str] = {}
    unattributed: bool = False
    for key, model in before.models.items():
        path: Path = before.model_paths[key]
        reason: str | None = _model_change(
            before=model, after=after.models[key], require_columns=path in edited
        )
        if reason is None:
            continue
        if path in edited:
            failing.setdefault(path, reason)
        else:
            unattributed = True
    empty: Counter[DiagnosticIdentity] = Counter()
    for owner in set(before.diagnostics) | set(after.diagnostics):
        previous: Counter[DiagnosticIdentity] = before.diagnostics.get(owner, empty)
        current: Counter[DiagnosticIdentity] = after.diagnostics.get(owner, empty)
        if owner in edited:
            added: Counter[DiagnosticIdentity] = current - previous
            if added:
                codes: str = ", ".join(sorted({identity[0] for identity in added}))
                failing.setdefault(owner, FIX_NEW_DIAGNOSTICS + codes)
        elif previous != current:
            unattributed = True
    return FixVerdict(failing=failing, unattributed=unattributed)


def _model_change(
    *, before: CompiledModel, after: CompiledModel, require_columns: bool
) -> str | None:
    """Edited models need known, equal columns; others must not change; absent lineage matches."""

    if require_columns and (before.inferred_columns is None or after.inferred_columns is None):
        return FIX_COLUMNS_UNKNOWN
    if before.inferred_columns != after.inferred_columns:
        return FIX_COLUMNS_CHANGED
    if before.deps != after.deps:
        return FIX_DEPENDENCIES_CHANGED
    lineage_before: object = (
        None if before.fast_lineage_columns is None else tuple(before.fast_lineage_columns)
    )
    lineage_after: object = (
        None if after.fast_lineage_columns is None else tuple(after.fast_lineage_columns)
    )
    if lineage_before != lineage_after:
        return FIX_LINEAGE_CHANGED
    return None
