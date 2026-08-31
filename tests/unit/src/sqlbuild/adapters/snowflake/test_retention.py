from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeRetentionTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRetentionTestCase(
            description="transient table retention is inspected and altered without conversion",
            desired_days=7,
            observed_row=(3, "YES"),
            expected_days=3,
            expected_kind="TRANSIENT",
            expected_sql=("ALTER TABLE racing.mart.results SET DATA_RETENTION_TIME_IN_DAYS = 7"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_relation_when_managing_retention_then_observes_and_renders_alter(
    test_case: SnowflakeRetentionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(row=test_case.observed_row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)
    request: RetentionRequest = RetentionRequest(
        request_id="model.results",
        scope=RetentionScope.RELATION,
        database="racing",
        schema="mart",
        name="results",
        desired_days=test_case.desired_days,
    )

    state: RetentionState = adapter.inspect_retention(
        connection=cast(Any, connection), request=request
    )
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(request=request)

    assert state.effective_days == test_case.expected_days
    assert state.relation_kind == test_case.expected_kind
    assert state.is_transient is True
    assert changes[0].phase == RetentionChangePhase.ALTER
    assert changes[0].statements == (test_case.expected_sql,)
    assert cursor.executed_sql is not None
    assert "retention_time, is_transient" in cursor.executed_sql
