"""Exact sharing of binding-mode native analyses between models with equal inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.analysis.reference_names import (
    _analysis_reference_name,
    _lineage_resource_type,
)
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def lineage_reference_map(
    references: tuple[CompileSqlReference, ...],
) -> dict[str, tuple[CompiledResourceType, str]]:
    reference_map: dict[str, tuple[CompiledResourceType, str]] = {}
    reference: CompileSqlReference
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        reference_map[_analysis_reference_name(reference)] = (
            resource_type,
            reference.ref_name,
        )
    return reference_map
