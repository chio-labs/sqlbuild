from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import InferredColumn
from sqlbuild.compiler.planner.models import BackfillResult, SchemaFinding


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
