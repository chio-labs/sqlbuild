"""BigQuery classification of stage clone failures that may fall back to a physical copy."""

from __future__ import annotations

import pytest
from google.api_core.exceptions import BadRequest, Forbidden, InternalServerError, TooManyRequests

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import MigrationStagePlan
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_connection import _BigQueryConnection
from tests.unit.src.sqlbuild.adapters.bigquery._test_types import BigQueryCloneRefusalTestCase
from tests.unit.src.sqlbuild.adapters.bigquery.helpers import FakeBigQueryFailingClient


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryCloneRefusalTestCase(
            description="clone chain depth limit is a refusal",
            driver_error=BadRequest(
                "clone chain too deep",
                errors=[
                    {
                        "reason": "invalid",
                        "message": "Cannot clone table: exceeded the limit of 3 clones or "
                        "snapshots in a chain; use a copy operation instead.",
                    }
                ],
            ),
            expected_refusal=True,
        ),
        BigQueryCloneRefusalTestCase(
            description="unsupported clone source is a refusal",
            driver_error=BadRequest(
                "unsupported clone source",
                errors=[{"reason": "invalidQuery", "message": "Clone is not supported for tables"}],
            ),
            expected_refusal=True,
        ),
        BigQueryCloneRefusalTestCase(
            description="backend error is transient and not a refusal",
            driver_error=InternalServerError(
                "backend",
                errors=[{"reason": "backendError", "message": "Cannot clone right now"}],
            ),
            expected_refusal=False,
        ),
        BigQueryCloneRefusalTestCase(
            description="rate limit is transient and not a refusal",
            driver_error=TooManyRequests(
                "rate",
                errors=[{"reason": "rateLimitExceeded", "message": "Cannot clone: rate limit"}],
            ),
            expected_refusal=False,
        ),
        BigQueryCloneRefusalTestCase(
            description="permission denial is not a refusal",
            driver_error=Forbidden(
                "denied",
                errors=[{"reason": "accessDenied", "message": "Access Denied: cannot clone"}],
            ),
            expected_refusal=False,
        ),
        BigQueryCloneRefusalTestCase(
            description="bad request without clone wording is not a refusal",
            driver_error=BadRequest(
                "missing",
                errors=[{"reason": "invalid", "message": "Dataset main was not found"}],
            ),
            expected_refusal=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_failure_when_classifying_then_only_capability_refusals_fall_back(
    test_case: BigQueryCloneRefusalTestCase,
) -> None:
    """Refusals are 400 invalid errors with clone-limitation wording, seen through the adapter."""

    adapter: BigQueryAdapter = BigQueryAdapter()
    plan: MigrationStagePlan = adapter.render_migration_stage(
        origin="analytics.orders", stage="analytics.orders_stage"
    )
    connection: _BigQueryConnection = _BigQueryConnection(
        client=FakeBigQueryFailingClient(query_error=test_case.driver_error), location="US"
    )

    with pytest.raises(AdapterUserError) as raised:
        _ = adapter.execute(connection=connection, sql=plan.statements[0])

    assert plan.is_clone_refusal is not None
    assert plan.is_clone_refusal(raised.value) is test_case.expected_refusal
    assert plan.fallback_statements == (
        "CREATE TABLE `analytics.orders_stage` COPY `analytics.orders`",
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
