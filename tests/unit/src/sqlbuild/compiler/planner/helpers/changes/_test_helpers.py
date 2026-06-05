"""Test helpers for change detection tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompileModelConfig,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.main.version_identity_metadata import (
    build_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.models import PlannerScope, WarehouseSnapshot
from sqlbuild.shared.helpers.hashing import compute_query_hash
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_types import (
    DetectModelChangesTestCase,
    DetectModelMetadataTestCase,
)

_STUB_TS: datetime = datetime(2026, 1, 15, 12, 0, 0)


def build_model_from_test_case(test_case: DetectModelChangesTestCase) -> CompiledModel:
    """Build a CompiledModel from a test case."""

    schema_entry: SchemaModelEntry | None = _build_schema_entry(test_case)
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=test_case.model_name),
        deps=(),
        name=test_case.model_name,
        relative_path=Path(f"models/{test_case.model_name}.sql"),
        query_sql=test_case.query_sql,
        config=CompileModelConfig(values=test_case.config_values),
        destination=CompiledRelationDestination(
            database=None, schema="staging", name=test_case.model_name, qualified_name=None
        ),
        schema_entry=schema_entry,
    )


def build_model_from_metadata_test_case(
    test_case: DetectModelMetadataTestCase,
) -> CompiledModel:
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        deps=tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name=dep_name)
            for dep_name in test_case.deps
        ),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="SELECT 1 AS order_id",
        config=CompileModelConfig(values=test_case.config_values),
        destination=CompiledRelationDestination(
            database=None, schema="staging", name="orders", qualified_name=None
        ),
        schema_entry=SchemaModelEntry(
            name="orders",
            columns=tuple(
                SchemaColumn(name=column[0], type=column[1], nullable=column[2])
                for column in test_case.schema_columns
            ),
        )
        if test_case.schema_columns
        else None,
    )


def build_snapshot_for_metadata_test_case(
    test_case: DetectModelMetadataTestCase,
) -> WarehouseSnapshot:
    return WarehouseSnapshot(
        existing_relations={
            "orders": RelationInfo(
                database=None,
                schema="staging",
                name="orders",
                relation_type="BASE TABLE",
            )
        },
        existing_columns={},
        fingerprints={
            "orders": Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash=compute_query_hash("SELECT 1 AS order_id"),
                ast_hash=None,
                schema_fingerprint="schema_a",
                query_sql="SELECT 1 AS order_id",
                metadata_json=test_case.previous_metadata_json,
                ts=_STUB_TS,
            )
        },
    )


def build_project_for_function_metadata_detection() -> CompiledProject:
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.FUNCTION,
        name="is_large_order",
    )
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        deps=(function_key,),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="SELECT is_large_order(amount) AS large_order FROM orders",
        config=CompileModelConfig(values={}),
        destination=CompiledRelationDestination(
            database=None, schema="staging", name="orders", qualified_name=None
        ),
    )
    function_destination: CompiledRelationDestination = CompiledRelationDestination(
        database=None,
        schema="staging",
        name="is_large_order",
        qualified_name=None,
    )
    function: CompiledFunction = CompiledFunction(
        key=function_key,
        deps=(),
        name="is_large_order",
        relative_path=Path("functions/is_large_order.sql"),
        arguments=(FunctionArgument(name="amount", type="INTEGER"),),
        returns="BOOLEAN",
        body_sql="amount > 100",
        destination=function_destination,
        fingerprint_destination=function_destination,
        language=FunctionLanguage.SQL,
    )
    return CompiledProject(
        run_id="run_001",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=(model,),
        functions=(function,),
    )


def build_scope_for_function_metadata_detection() -> PlannerScope:
    model_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.FUNCTION,
        name="is_large_order",
    )
    project: CompiledProject = build_project_for_function_metadata_detection()
    return PlannerScope(
        upstream_deps={model_key: (function_key,), function_key: ()},
        downstream_deps={function_key: (model_key,), model_key: ()},
        all_keys={"orders": model_key, "is_large_order": function_key},
        models_by_name={"orders": project.models[0]},
        selected_keys=frozenset({model_key}),
        execution_order=(function_key, model_key),
    )


def build_snapshot_from_test_case(test_case: DetectModelChangesTestCase) -> WarehouseSnapshot:
    """Build a WarehouseSnapshot from a test case."""

    relations: dict[str, RelationInfo] = _build_relations(test_case)
    columns: dict[str, tuple[ColumnInfo, ...]] = _build_columns(test_case)
    fingerprints: dict[str, Fingerprint] = _build_fingerprints(test_case)
    return WarehouseSnapshot(
        existing_relations=relations,
        existing_columns=columns,
        fingerprints=fingerprints,
    )


def _build_schema_entry(test_case: DetectModelChangesTestCase) -> SchemaModelEntry | None:
    schema_cols: tuple[tuple[str, str | None], ...] = test_case.schema_columns
    if not schema_cols:
        return None
    return SchemaModelEntry(
        name=test_case.model_name,
        columns=tuple(SchemaColumn(name=c[0], type=c[1]) for c in schema_cols),
    )


def _build_relations(test_case: DetectModelChangesTestCase) -> dict[str, RelationInfo]:
    if not test_case.relation_exists:
        return {}
    return {
        test_case.model_name: RelationInfo(
            database=None,
            schema="staging",
            name=test_case.model_name,
            relation_type="BASE TABLE",
        )
    }


def _build_columns(
    test_case: DetectModelChangesTestCase,
) -> dict[str, tuple[ColumnInfo, ...]]:
    if not test_case.warehouse_column_names:
        return {}
    return {
        test_case.model_name: tuple(
            ColumnInfo(name=c[0], type=c[1]) for c in test_case.warehouse_column_names
        )
    }


def _build_fingerprints(test_case: DetectModelChangesTestCase) -> dict[str, Fingerprint]:
    if test_case.fingerprint_query_hash is None:
        return {}
    fingerprint_config_values: dict[str, object] = (
        test_case.config_values
        if test_case.fingerprint_config_values is None
        else test_case.fingerprint_config_values
    )
    return {
        test_case.model_name: Fingerprint(
            model_name=test_case.model_name,
            target_database=None,
            target_schema=None,
            target_name=test_case.model_name,
            run_id="run_001",
            query_hash=test_case.fingerprint_query_hash,
            ast_hash=test_case.fingerprint_ast_hash,
            schema_fingerprint="schema_a",
            query_sql="SELECT 1",
            metadata_json=build_version_identity_metadata_json(
                model_name=test_case.model_name,
                config_values=fingerprint_config_values,
            ),
            ts=_STUB_TS,
        )
    }
