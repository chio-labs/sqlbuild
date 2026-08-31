from typing import Any

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import RenderedRetentionChange, RetentionState
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from tests.unit.src.sqlbuild.adapters.databricks._test_types import (
    DatabricksInvalidRetentionTestCase,
    DatabricksRetentionOrderingTestCase,
    DatabricksRetentionTestCase,
)
from tests.unit.src.sqlbuild.adapters.databricks.helpers import (
    FakeDatabricksMetadataConnection,
    FakeDatabricksMetadataCursor,
    build_retention_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksRetentionTestCase(
            description="Delta intervals are parsed and changed together",
            desired_days=14,
            observed_row=(
                "delta",
                {
                    "delta.logRetentionDuration": "interval 30 days",
                    "delta.deletedFileRetentionDuration": "INTERVAL 7 DAYS",
                },
            ),
            expected_effective_days=7,
            expected_sql=(
                "ALTER TABLE `main`.`mart`.`results` SET TBLPROPERTIES "
                "('delta.logRetentionDuration' = 'interval 14 days', "
                "'delta.deletedFileRetentionDuration' = 'interval 14 days')"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_delta_relation_when_managing_retention_then_parses_and_renders_properties(
    test_case: DatabricksRetentionTestCase,
) -> None:
    cursor: FakeDatabricksMetadataCursor = FakeDatabricksMetadataCursor(
        rows=[test_case.observed_row]
    )
    connection: FakeDatabricksMetadataConnection = FakeDatabricksMetadataConnection((cursor,))
    adapter: DatabricksAdapter = DatabricksAdapter()

    state: RetentionState = adapter.inspect_retention(
        connection=connection,
        request=build_retention_request(desired_days=test_case.desired_days),
    )
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
        request=build_retention_request(desired_days=test_case.desired_days)
    )

    assert state.effective_days == test_case.expected_effective_days
    assert state.delta_log_retention_days == 30
    assert state.delta_deleted_file_retention_days == 7
    assert cursor.executed_sql == "DESCRIBE DETAIL `main`.`mart`.`results`"
    assert changes[0].statements == (test_case.expected_sql,)
    assert "VACUUM" not in changes[0].statements[0]


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksRetentionOrderingTestCase(
            description="mixed values increase deleted files before decreasing log history",
            desired_days=14,
            log_days=30,
            deleted_days=7,
            expected_phases=("prepare", "finalize"),
            expected_property_order=("deletedFileRetentionDuration", "logRetentionDuration"),
        ),
        DatabricksRetentionOrderingTestCase(
            description="decreases lower deleted files before log history",
            desired_days=7,
            log_days=30,
            deleted_days=14,
            expected_phases=("finalize", "finalize"),
            expected_property_order=("deletedFileRetentionDuration", "logRetentionDuration"),
        ),
        DatabricksRetentionOrderingTestCase(
            description="repairs an inconsistent warehouse state before decreasing",
            desired_days=14,
            log_days=7,
            deleted_days=30,
            expected_phases=("prepare", "finalize", "finalize"),
            expected_property_order=(
                "logRetentionDuration",
                "deletedFileRetentionDuration",
                "logRetentionDuration",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_independent_delta_values_when_rendering_then_preserves_retention_invariant(
    test_case: DatabricksRetentionOrderingTestCase,
) -> None:
    changes: tuple[RenderedRetentionChange, ...] = DatabricksAdapter().render_retention_changes(
        request=build_retention_request(desired_days=test_case.desired_days),
        state=RetentionState(
            request_id="results",
            scope=build_retention_request(desired_days=test_case.desired_days).scope,
            configured_days=None,
            effective_days=min(test_case.log_days, test_case.deleted_days),
            delta_log_retention_days=test_case.log_days,
            delta_deleted_file_retention_days=test_case.deleted_days,
        ),
    )

    assert tuple(change.phase.value for change in changes) == test_case.expected_phases
    assert tuple(
        property_name in change.statements[0]
        for property_name, change in zip(test_case.expected_property_order, changes, strict=True)
    ) == tuple(True for _ in test_case.expected_property_order)
    assert all("VACUUM" not in change.statements[0] for change in changes)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksInvalidRetentionTestCase(
            description="non Delta relation is rejected",
            observed_row=("parquet", {}),
            expected_error_fragment="requires a Delta relation",
        ),
        DatabricksInvalidRetentionTestCase(
            description="unparseable Delta interval is rejected",
            observed_row=(
                "delta",
                {
                    "delta.logRetentionDuration": "30 days",
                    "delta.deletedFileRetentionDuration": "interval 7 days",
                },
            ),
            expected_error_fragment="unparseable",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_delta_metadata_when_inspecting_retention_then_raises_clear_error(
    test_case: DatabricksInvalidRetentionTestCase,
) -> None:
    cursor: FakeDatabricksMetadataCursor = FakeDatabricksMetadataCursor(
        rows=[test_case.observed_row]
    )
    connection: Any = FakeDatabricksMetadataConnection((cursor,))

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        DatabricksAdapter().inspect_retention(
            connection=connection, request=build_retention_request(desired_days=7)
        )
