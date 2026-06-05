from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.detect import detect_changes, detect_model_changes
from sqlbuild.compiler.planner.main.version_identity_metadata import (
    build_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerScope,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from sqlbuild.shared.helpers.hashing import compute_query_hash
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_helpers import (
    build_model_from_metadata_test_case,
    build_model_from_test_case,
    build_project_for_function_metadata_detection,
    build_scope_for_function_metadata_detection,
    build_snapshot_for_metadata_test_case,
    build_snapshot_from_test_case,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.changes._test_types import (
    DetectModelChangesTestCase,
    DetectModelMetadataTestCase,
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
    DetectModelChangesTestCase(
        description="detects config change when version identity config differs",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={"materialized": "table"},
        fingerprint_config_values={"materialized": "view"},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_MATCHING_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.CONFIG_CHANGED,
        expected_backfill_action=BackfillAction.WARN_ONLY,
    ),
    DetectModelChangesTestCase(
        description="ignores unknown config differences",
        model_name="orders",
        query_sql=_QUERY_SQL,
        config_values={"future_default_flag": "off"},
        fingerprint_config_values={},
        schema_columns=(),
        relation_exists=True,
        fingerprint_query_hash=_MATCHING_HASH,
        fingerprint_ast_hash=None,
        warehouse_column_names=(),
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.WARN_ONLY,
    ),
]

DETECT_MODEL_METADATA_TEST_CASES: list[DetectModelMetadataTestCase] = [
    DetectModelMetadataTestCase(
        description="detects config change when dependent function hash changes",
        config_values={},
        schema_columns=(),
        deps=("is_large_order",),
        function_local_hashes={"is_large_order": "new"},
        previous_metadata_json=build_version_identity_metadata_json(
            model_name="orders",
            config_values={},
            local_function_hashes={"is_large_order": "old"},
        ),
        expected_change_kind=ChangeKind.CONFIG_CHANGED,
        expected_metadata_fragments=('"local_function_hashes":{"is_large_order":"new"}',),
    ),
    DetectModelMetadataTestCase(
        description="detects config change when execution signature changes",
        config_values={"contract": "enforced"},
        schema_columns=(("order_id", "INTEGER", False),),
        deps=(),
        function_local_hashes={},
        previous_metadata_json=build_version_identity_metadata_json(
            model_name="orders",
            config_values={"contract": "enforced"},
            execution_signature={},
        ),
        expected_change_kind=ChangeKind.CONFIG_CHANGED,
        expected_metadata_fragments=(
            '"execution_signature":{"contract":{"columns":[{"name":"order_id",'
            '"nullable":false,"type":"INTEGER"}],"enforced":true}}',
        ),
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


@pytest.mark.parametrize(
    "test_case",
    DETECT_MODEL_METADATA_TEST_CASES,
    ids=[case.description for case in DETECT_MODEL_METADATA_TEST_CASES],
)
def test_given_model_identity_metadata_when_detecting_changes_then_uses_aligned_metadata(
    test_case: DetectModelMetadataTestCase,
) -> None:
    model: CompiledModel = build_model_from_metadata_test_case(test_case)
    snapshot: WarehouseSnapshot = build_snapshot_for_metadata_test_case(test_case)

    result: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=snapshot,
        sqlglot_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        function_local_hashes=test_case.function_local_hashes,
    )

    assert result.change_kind == test_case.expected_change_kind
    fragment: str
    for fragment in test_case.expected_metadata_fragments:
        assert fragment in (result.fingerprint_metadata_json or "")


@pytest.mark.parametrize(
    "test_case",
    [
        DetectModelMetadataTestCase(
            description="direct project function hash change marks dependent model changed",
            config_values={},
            schema_columns=(),
            deps=("is_large_order",),
            function_local_hashes={"is_large_order": "old"},
            previous_metadata_json="{}",
            expected_change_kind=ChangeKind.CONFIG_CHANGED,
        )
    ],
    ids=["direct project function hash change marks dependent model changed"],
)
def test_given_direct_project_function_hash_change_when_detecting_changes_then_model_is_changed(
    test_case: DetectModelMetadataTestCase,
) -> None:
    scope: PlannerScope = build_scope_for_function_metadata_detection()
    snapshot: WarehouseSnapshot = WarehouseSnapshot(
        existing_relations=build_snapshot_for_metadata_test_case(
            DetectModelMetadataTestCase(
                description="snapshot relation",
                config_values={},
                schema_columns=(),
                deps=(),
                function_local_hashes={},
                previous_metadata_json="{}",
                expected_change_kind=ChangeKind.NO_CHANGE,
            )
        ).existing_relations,
        existing_columns={},
        fingerprints={
            "orders": Fingerprint(
                model_name="orders",
                target_database=None,
                target_schema=None,
                target_name="orders",
                run_id="run_001",
                query_hash=compute_query_hash(
                    "SELECT is_large_order(amount) AS large_order FROM orders"
                ),
                ast_hash=None,
                schema_fingerprint="schema_a",
                query_sql="SELECT is_large_order(amount) AS large_order FROM orders",
                metadata_json=build_version_identity_metadata_json(
                    model_name="orders",
                    config_values={},
                    local_function_hashes=test_case.function_local_hashes,
                ),
                ts=datetime(2026, 1, 15, 12, 0, 0),
            )
        },
    )

    result: PlannerChangeResults = detect_changes(
        project=build_project_for_function_metadata_detection(),
        scope=scope,
        snapshot=snapshot,
        full_refresh=False,
    )

    assert result.models["orders"].change_kind == test_case.expected_change_kind
