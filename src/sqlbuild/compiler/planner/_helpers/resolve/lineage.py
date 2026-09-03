"""Resolve declared cursor inputs from transitive SQL resource lineage."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompileSqlReference,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.references.types import SqlReferenceKind


def resolve_lineage_reference(
    *,
    model: CompiledModel,
    input_name: str,
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction],
) -> CompileSqlReference:
    """Resolve one named input through model and SQL function references."""

    pending: list[CompileSqlReference] = list(model.references)
    visited: set[tuple[str, str]] = set()
    while pending:
        reference: CompileSqlReference = pending.pop(0)
        if reference.ref_name == input_name:
            return reference
        identity: tuple[str, str] = (reference.ref_kind, reference.ref_name)
        if identity in visited:
            continue
        visited.add(identity)
        if reference.ref_kind == SqlReferenceKind.REF:
            upstream_model: CompiledModel | None = models_by_name.get(reference.ref_name)
            if upstream_model is not None:
                pending.extend(upstream_model.references)
        elif reference.ref_kind in {
            SqlReferenceKind.UDF,
            SqlReferenceKind.TABLE_FUNCTION,
        }:
            upstream_function: CompiledFunction | None = functions_by_name.get(reference.ref_name)
            if upstream_function is not None:
                pending.extend(upstream_function.references)
    raise PlannerInputError(
        f"model '{model.name}': cursor_inputs watermark references '{input_name}', but it is "
        "not in the model's upstream lineage",
        code="S302",
    )
