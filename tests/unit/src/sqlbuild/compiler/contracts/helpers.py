from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry


def make_contract_project(
    *,
    declared_columns: tuple[tuple[str, str | None], ...],
    inferred_columns: tuple[tuple[str, str | None], ...] | None,
    type_enforcement: bool | None,
    model_name: str = "orders",
) -> CompiledProject:
    """Build a compiled project for contract validation tests."""

    key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name=model_name,
    )
    return CompiledProject(
        run_id="run-1",
        effective_environment_name="dev",
        effective_connection={},
        effective_vars={},
        models=(
            CompiledModel(
                key=key,
                deps=(),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql="SELECT 1 AS id",
                config=CompileModelConfig(values={}),
                target=CompiledRelationTarget(
                    database=None,
                    schema="analytics",
                    name=model_name,
                    qualified_name=f"analytics.{model_name}",
                ),
                schema_entry=SchemaModelEntry(
                    name=model_name,
                    type_enforcement=type_enforcement,
                    columns=tuple(
                        SchemaColumn(name=name, type=column_type)
                        for name, column_type in declared_columns
                    ),
                ),
                inferred_columns=None
                if inferred_columns is None
                else tuple(
                    InferredColumn(name=name, type=column_type)
                    for name, column_type in inferred_columns
                ),
            ),
        ),
    )
