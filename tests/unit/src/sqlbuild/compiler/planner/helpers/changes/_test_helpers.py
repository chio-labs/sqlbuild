"""Test helpers for change detection tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.main.version_identity_metadata import (
    build_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.models import WarehouseSnapshot
from sqlbuild.spec.models.schema import SchemaColumn, SchemaModelEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_types import (
    DetectModelChangesTestCase,
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
        target=CompiledRelationTarget(
            database=None, schema="staging", name=test_case.model_name, qualified_name=None
        ),
        schema_entry=schema_entry,
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
