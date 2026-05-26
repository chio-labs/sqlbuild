from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.planner.helpers.changes.detect import detect_model_changes
from sqlbuild.compiler.planner.models import ChangeDetectionResult, WarehouseSnapshot
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from sqlbuild.shared.helpers.hashing import compute_query_hash
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_helpers import (
    build_model_from_test_case,
    build_snapshot_from_test_case,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_types import (
    DetectModelChangesTestCase,
)

_QUERY_SQL: str = "SELECT id, name FROM orders"
_MATCHING_HASH: str = compute_query_hash(_QUERY_SQL)
_DIFFERENT_HASH: str = "completely_different_hash"

DETECT_MODEL_CHANGES_TEST_CASES: list[DetectModelChangesTestCase] = [
    DetectModelChangesTestCase(
        description="detects first run when relation and fingerprint are missing",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={},
        schema_columns=(),
        relation_exists=False,
        fingerprint_query_hash=None,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.FIRST_RUN,
        expected_backfill_action=BackfillAction.FULL,
    ),
    DetectModelChangesTestCase(
        description="detects no change when query hash matches and no schema columns declared",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_MATCHING_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(("id", "INTEGER"), ("name", "VARCHAR")),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.WARN_ONLY,
    ),
    DetectModelChangesTestCase(
        description="detects query change when hash differs",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={"query_change_backfill": "bounded-30d"},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_DIFFERENT_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
    ),
    DetectModelChangesTestCase(
        description="detects schema change when expected column is missing from warehouse",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={"schema_change_backfill": {"add_column": "full"}},
        schema_columns=(("id", "INTEGER"), ("status", "VARCHAR")),
        relation_exists=True,
        fingerprint_query_hash=_MATCHING_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(("id", "INTEGER"),),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.SCHEMA_CHANGED,
        expected_backfill_action=BackfillAction.FULL,
    ),
    DetectModelChangesTestCase(
        description="returns full backfill when full refresh is requested",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_MATCHING_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=True,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FULL,
    ),
    DetectModelChangesTestCase(
        description="skips query change detection when tracking is disabled",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_DIFFERENT_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=False,
        full_refresh=False,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.WARN_ONLY,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DETECT_MODEL_CHANGES_TEST_CASES,
    ids=[case.description for case in DETECT_MODEL_CHANGES_TEST_CASES],
)
def test_given_model_and_snapshot_when_detecting_changes_then_returns_expected(
    test_case: DetectModelChangesTestCase,
) -> None:
    model: CompiledModel = build_model_from_test_case(test_case)
    snapshot: WarehouseSnapshot = build_snapshot_from_test_case(test_case)

    result: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=snapshot,
        sqlglot_enabled=test_case.sqlglot_enabled,
        query_change_tracking=test_case.query_change_tracking,
        full_refresh=test_case.full_refresh,
    )

    assert result.change_kind == test_case.expected_change_kind
    assert result.backfill.action == test_case.expected_backfill_action
