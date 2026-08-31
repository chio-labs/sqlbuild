import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_connection import _BigQueryConnection
from tests.unit.src.sqlbuild.adapters.bigquery._test_types import (
    BigQueryInvalidRetentionTestCase,
    BigQueryRetentionTestCase,
)
from tests.unit.src.sqlbuild.adapters.bigquery.helpers import (
    FakeBigQueryClient,
    FakeBigQueryDataset,
    build_retention_request,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRetentionTestCase(
            description="dataset time travel hours are inspected and rendered from days",
            desired_days=5,
            expected_hours=120,
            expected_sql=(
                "ALTER SCHEMA `racing-prod.mart` SET OPTIONS (max_time_travel_hours = 120)"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_namespace_when_managing_retention_then_uses_dataset_metadata_and_ddl(
    test_case: BigQueryRetentionTestCase,
) -> None:
    client: FakeBigQueryClient = FakeBigQueryClient(
        dataset=FakeBigQueryDataset(max_time_travel_hours=test_case.expected_hours)
    )
    connection: _BigQueryConnection = _BigQueryConnection(client=client, location=None)
    request: RetentionRequest = build_retention_request(desired_days=test_case.desired_days)
    adapter: BigQueryAdapter = BigQueryAdapter()

    state: RetentionState = adapter.inspect_retention(connection=connection, request=request)
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(request=request)

    assert state.max_time_travel_hours == test_case.expected_hours
    assert state.effective_days == test_case.desired_days
    assert changes[0].statements == (test_case.expected_sql,)
    assert client.dataset_ids == ["racing-prod.mart"]


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryInvalidRetentionTestCase(
            description="one day is below the BigQuery boundary",
            desired_days=1,
            expected_error_fragment="between 2 and 7",
        ),
        BigQueryInvalidRetentionTestCase(
            description="eight days is above the BigQuery boundary",
            desired_days=8,
            expected_error_fragment="between 2 and 7",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_out_of_range_days_when_rendering_bigquery_retention_then_raises_clear_error(
    test_case: BigQueryInvalidRetentionTestCase,
) -> None:
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        BigQueryAdapter().render_retention_changes(
            request=build_retention_request(desired_days=test_case.desired_days)
        )
