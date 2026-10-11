"""Exact sharing of binding-mode native analyses between models with equal inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.analysis.reference_names import (
    table_function_analysis_name,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.references.types import SqlReferenceKind

_LINEAGE_RESOURCE_TYPES: dict[str, CompiledResourceType] = {
    SqlReferenceKind.REF: CompiledResourceType.MODEL,
    SqlReferenceKind.SOURCE: CompiledResourceType.SOURCE,
    SqlReferenceKind.SEED: CompiledResourceType.SEED,
    SqlReferenceKind.TABLE_FUNCTION: CompiledResourceType.TABLE_FN,
}


def lineage_reference_map(
    rows: list[tuple[str, str, str | None, int | None]],
) -> dict[str, tuple[CompiledResourceType, str]]:
    """Each lineage reference's analysis name, from `(kind, name, package, count)` rows."""

    reference_map: dict[str, tuple[CompiledResourceType, str]] = {}
    for kind, name, _, _ in rows:
        resource_type: CompiledResourceType | None = _LINEAGE_RESOURCE_TYPES.get(kind)
        if resource_type is None:
            continue
        analysis_name: str = (
            table_function_analysis_name(name) if kind == SqlReferenceKind.TABLE_FUNCTION else name
        )
        reference_map[analysis_name] = (resource_type, name)
    return reference_map
