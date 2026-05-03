from dataclasses import dataclass

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
