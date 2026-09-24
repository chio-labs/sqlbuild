"""Compatibility of a migration origin relation with its destination model."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ColumnInfo, NormalizedType, RelationInfo
from sqlbuild.adapter.contract.types import TypeFamily
from sqlbuild.adapter.type_system.main.normalize_type import normalize_type
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.migrations.types import MigrationCompatibility
from sqlbuild.compiler.planner._helpers.changes.detect import detect_model_changes
from sqlbuild.compiler.planner.constants import VIEW_RELATION_TYPE_MARKER
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    MigrationCompatibilityResult,
    SchemaFinding,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    OnSchemaChange,
    SchemaChangeKind,
    SnapshotSchemaChangePolicy,
)
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import SnapshotsConfig

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_NUMERIC_FAMILIES: frozenset[TypeFamily] = frozenset(
    {TypeFamily.INTEGER, TypeFamily.DECIMAL, TypeFamily.FLOAT}
)
_TEMPORAL_FAMILIES: frozenset[TypeFamily] = frozenset(
    {TypeFamily.TIMESTAMP, TypeFamily.DATE, TypeFamily.DATETIME}
)


def check_migration_compatibility(
    *,
    model: CompiledModel,
    origin_relation: RelationInfo,
    origin_columns: tuple[ColumnInfo, ...],
    sql_analysis_enabled: bool,
    column_dialect: str | None,
    snapshots_config: SnapshotsConfig,
) -> MigrationCompatibilityResult:
    """Check the origin exactly as a normal build would check an existing destination."""

    if VIEW_RELATION_TYPE_MARKER in origin_relation.relation_type.upper():
        return MigrationCompatibilityResult(
            status=MigrationCompatibility.INCOMPATIBLE,
            findings=("origin relation is a view; only tables carry migratable history",),
        )
    change: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=WarehouseSnapshot(
            existing_relations={model.name: origin_relation},
            existing_columns={model.name: origin_columns},
            column_dialect=column_dialect,
        ),
        sql_analysis_enabled=sql_analysis_enabled,
        query_change_tracking=False,
        full_refresh=False,
    )
    if not _has_expected_columns(model=model):
        return MigrationCompatibilityResult(status=MigrationCompatibility.NOT_CHECKED)
    materialized: str | None = get_config_str(values=model.config.values, key="materialized")
    blocking: tuple[str, ...] = (
        _snapshot_blocking_findings(
            model=model,
            findings=change.schema_findings,
            dialect=column_dialect,
            snapshots_config=snapshots_config,
        )
        if materialized == MaterializationType.SNAPSHOT
        else _incremental_blocking_findings(
            model=model, findings=change.schema_findings, dialect=column_dialect
        )
    )
    if blocking:
        return MigrationCompatibilityResult(
            status=MigrationCompatibility.INCOMPATIBLE, findings=blocking
        )
    return MigrationCompatibilityResult(status=MigrationCompatibility.COMPATIBLE)


def _has_expected_columns(*, model: CompiledModel) -> bool:
    if model.schema_entry is not None and any(
        column.type is not None for column in model.schema_entry.columns
    ):
        return True
    return bool(model.inferred_columns)


def _incremental_blocking_findings(
    *, model: CompiledModel, findings: tuple[SchemaFinding, ...], dialect: str | None
) -> tuple[str, ...]:
    raw_policy: str | None = get_config_str(values=model.config.values, key="on_schema_change")
    policy: OnSchemaChange = OnSchemaChange(raw_policy) if raw_policy else _DEFAULT_ON_SCHEMA_CHANGE
    blocking: list[str] = []
    finding: SchemaFinding
    for finding in findings:
        if policy == OnSchemaChange.FAIL:
            blocking.append(f"{_describe(finding)} (on_schema_change fail)")
            continue
        if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED and not _types_convertible(
            expected=finding.expected_type, actual=finding.actual_type, dialect=dialect
        ):
            blocking.append(f"{_describe(finding)} (incompatible types)")
    return tuple(blocking)


def _snapshot_blocking_findings(
    *,
    model: CompiledModel,
    findings: tuple[SchemaFinding, ...],
    dialect: str | None,
    snapshots_config: SnapshotsConfig,
) -> tuple[str, ...]:
    raw_policy: str | None = get_config_str(
        values=model.config.values, key="snapshot_schema_change"
    )
    policy: SnapshotSchemaChangePolicy = SnapshotSchemaChangePolicy(
        raw_policy or snapshots_config.schema_change
    )
    blocking: list[str] = []
    finding: SchemaFinding
    for finding in findings:
        if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED and not _string_widening(
            expected=finding.expected_type, actual=finding.actual_type, dialect=dialect
        ):
            blocking.append(f"{_describe(finding)} (snapshot type change)")
        elif (
            finding.kind == SchemaChangeKind.COLUMN_ADDED
            and policy == SnapshotSchemaChangePolicy.DENY
        ):
            blocking.append(f"{_describe(finding)} (snapshot_schema_change deny)")
    return tuple(blocking)


def _types_convertible(*, expected: str | None, actual: str | None, dialect: str | None) -> bool:
    if expected is None or actual is None:
        return True
    expected_family: TypeFamily = normalize_type(type_sql=expected, dialect=dialect).family
    actual_family: TypeFamily = normalize_type(type_sql=actual, dialect=dialect).family
    if TypeFamily.OTHER in {expected_family, actual_family}:
        return True
    if expected_family == actual_family:
        return True
    if {expected_family, actual_family} <= _NUMERIC_FAMILIES:
        return True
    return {expected_family, actual_family} <= _TEMPORAL_FAMILIES


def _string_widening(*, expected: str | None, actual: str | None, dialect: str | None) -> bool:
    if expected is None or actual is None:
        return True
    target: NormalizedType = normalize_type(type_sql=actual, dialect=dialect)
    incoming: NormalizedType = normalize_type(type_sql=expected, dialect=dialect)
    if target == incoming:
        return True
    if target.family != TypeFamily.STRING or incoming.family != TypeFamily.STRING:
        return False
    if target.length is None:
        return True
    return incoming.length is not None and incoming.length <= target.length


def _describe(finding: SchemaFinding) -> str:
    if finding.kind == SchemaChangeKind.COLUMN_ADDED:
        return f"column {finding.column_name} is missing from the origin"
    if finding.kind == SchemaChangeKind.COLUMN_REMOVED:
        return f"origin column {finding.column_name} is not produced by the model"
    return (
        f"column {finding.column_name} is {finding.actual_type} in the origin but the model "
        f"produces {finding.expected_type}"
    )
