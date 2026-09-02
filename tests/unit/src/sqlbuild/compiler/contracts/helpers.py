from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SettingsConfig,
    SourceLocation,
)
from sqlbuild.spec.contracts.types import ColumnContractMode


def make_contract_project(
    *,
    declared_columns: tuple[tuple[str, str | None], ...],
    inferred_columns: tuple[tuple[str, str | None], ...] | None,
    type_enforcement: bool | None,
    contract: str | None = None,
    column_contract_mode: str = "implicit",
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
        settings=SettingsConfig(column_contract_mode=ColumnContractMode(column_contract_mode)),
        models=(
            CompiledModel(
                key=key,
                deps=(),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql="SELECT 1 AS id",
                config=CompileModelConfig(
                    values=cast(
                        dict[str, object],
                        ({}, {"contract": contract})[contract is not None],
                    )
                ),
                destination=CompiledRelationLocation(
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
                inferred_columns=(
                    None,
                    tuple(
                        InferredColumn(
                            name=name,
                            type=column_type,
                            nullability=(inferred_nullability_by_column or {}).get(
                                name, InferredNullability.UNKNOWN
                            ),
                        )
                        for name, column_type in (inferred_columns or ())
                    ),
                )[inferred_columns is not None],
            ),
        ),
    )


def _column_audits(
    *, name: str, declared_not_null_columns: tuple[str, ...]
) -> tuple[SchemaAuditInstance, ...]:
    return ((), (SchemaAuditInstance(definition_name="not_null"),))[
        name in declared_not_null_columns
    ]
