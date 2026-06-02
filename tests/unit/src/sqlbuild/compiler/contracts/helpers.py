from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.models.schema import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SourceLocation,
)


def make_contract_project(
    *,
    declared_columns: tuple[tuple[str, str | None], ...],
    inferred_columns: tuple[tuple[str, str | None], ...] | None,
    type_enforcement: bool | None,
    contract: str | None = None,
    model_name: str = "orders",
    column_locations: dict[str, SourceLocation] | None = None,
    declared_not_null_columns: tuple[str, ...] = (),
    declared_nullable_by_column: dict[str, bool | None] | None = None,
    inferred_nullability_by_column: dict[str, InferredNullability] | None = None,
) -> CompiledProject:
    """Build a compiled project for contract validation tests."""

    key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name=model_name,
    )
    return CompiledProject(
        run_id="run-1",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        models=(
            CompiledModel(
                key=key,
                deps=(),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql="SELECT 1 AS id",
                config=CompileModelConfig(
                    values={} if contract is None else {"contract": contract}
                ),
                destination=CompiledRelationDestination(
                    database=None,
                    schema="analytics",
                    name=model_name,
                    qualified_name=f"analytics.{model_name}",
                ),
                schema_entry=SchemaModelEntry(
                    name=model_name,
                    type_enforcement=type_enforcement,
                    columns=tuple(
                        SchemaColumn(
                            name=name,
                            type=column_type,
                            audits=_column_audits(
                                name=name,
                                declared_not_null_columns=declared_not_null_columns,
                            ),
                            nullable=(declared_nullable_by_column or {}).get(name),
                            location=(column_locations or {}).get(name),
                        )
                        for name, column_type in declared_columns
                    ),
                ),
                inferred_columns=None
                if inferred_columns is None
                else tuple(
                    InferredColumn(
                        name=name,
                        type=column_type,
                        nullability=(inferred_nullability_by_column or {}).get(
                            name, InferredNullability.UNKNOWN
                        ),
                    )
                    for name, column_type in inferred_columns
                ),
            ),
        ),
    )


def _column_audits(
    *, name: str, declared_not_null_columns: tuple[str, ...]
) -> tuple[SchemaAuditInstance, ...]:
    if name not in declared_not_null_columns:
        return ()
    return (SchemaAuditInstance(definition_name="not_null"),)
