from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import InferredColumn
from sqlbuild.compiler.planner.models import BackfillResult, SchemaFinding
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind


@dataclass(frozen=True)
class DetectModelChangesTestCase:
    description: str
    model_name: str
    query_sql: str
    config_values: dict[str, object]
    schema_columns: tuple[tuple[str, str | None], ...]
    relation_exists: bool
    fingerprint_query_hash: str | None
    fingerprint_ast_hash: str | None
    warehouse_column_names: tuple[tuple[str, str], ...]
    sqlglot_enabled: bool
    query_change_tracking: bool
    full_refresh: bool
    expected_change_kind: ChangeKind
    expected_backfill_action: BackfillAction
    fingerprint_config_values: dict[str, object] | None = None


@dataclass(frozen=True)
class DetectQueryChangeTestCase:
    description: str
    compiled_query_hash: str
    compiled_ast_hash: str | None
    fingerprint_query_hash: str
    fingerprint_ast_hash: str | None
    sqlglot_enabled: bool
    expected_changed: bool


@dataclass(frozen=True)
class DetectSchemaChangesTestCase:
    description: str
    yml_columns: tuple[ColumnInfo, ...]
    inferred_columns: tuple[InferredColumn, ...] | None
    warehouse_columns: tuple[ColumnInfo, ...]
    type_enforcement: bool
    expected_findings: tuple[SchemaFinding, ...]


@dataclass(frozen=True)
class ResolveBackfillTestCase:
    description: str
    raw_value: str | None
    expected_result: BackfillResult


@dataclass(frozen=True)
class ResolveSchemaBackfillTestCase:
    description: str
    schema_change_backfill: dict[str, str]
    findings: tuple[SchemaFinding, ...]
    expected_result: BackfillResult
