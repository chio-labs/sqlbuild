"""Test helpers for audit rendering tests."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.spec.models.source import SourceEntry


def build_render_model_targets(
    targets: dict[str, str],
) -> dict[str, CompiledRelationTarget]:
    """Build model targets from a simple name-to-qualified mapping."""

    return {
        name: CompiledRelationTarget(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }


def build_render_seed_targets(
    targets: dict[str, str],
) -> dict[str, CompiledRelationTarget]:
    """Build seed targets from a simple name-to-qualified mapping."""

    return {
        name: CompiledRelationTarget(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }


def build_render_source_map(
    entries: dict[str, tuple[str | None, str | None, str | None]],
) -> dict[str, SourceEntry]:
    """Build source map from simple tuples of (database, schema, table)."""

    return {
        name: SourceEntry(
            name=name,
            database=parts[0],
            schema=parts[1],
            table=parts[2],
        )
        for name, parts in entries.items()
    }
