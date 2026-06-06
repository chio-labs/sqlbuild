from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.main.helpers.freshness.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.cli.commands.main.helpers.freshness.output import (
    format_freshness_json,
    format_freshness_text,
)
from sqlbuild.cli.commands.main.helpers.freshness.types import FreshnessSourceStatus
from tests.unit.src.sqlbuild.cli.commands.main.helpers.freshness._test_types import (
    FreshnessOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessOutputTestCase(
            description="formats observed unknown and error sources",
            result=FreshnessCommandResult(
                sources=(
                    FreshnessSourceResult(
                        name="raw_orders",
                        status=FreshnessSourceStatus.OBSERVED,
                        strategy="timestamp",
                        value_kind="timestamp",
                        current_data_version="2026-01-01T00:00:00",
                        lag_tolerance="15m",
                    ),
                    FreshnessSourceResult(
                        name="raw_payments",
                        status=FreshnessSourceStatus.UNKNOWN,
                        message="no freshness config and adapter metadata unavailable",
                    ),
                    FreshnessSourceResult(
                        name="raw_events",
                        status=FreshnessSourceStatus.ERROR,
                        message="freshness query failed",
                    ),
                )
            ),
            expected_text_fragments=(
                "Observed (1)",
                "raw_orders  timestamp  2026-01-01T00:00:00  timestamp  tolerance 15m",
                "Unknown (1)",
                "raw_payments  no freshness config and adapter metadata unavailable",
                "Errors (1)",
                "raw_events  freshness query failed",
                "Summary: observed=1 changed=0 unchanged=0 tolerated=0 unknown=1 errors=1",
            ),
            expected_summary={
                "observed": 1,
                "changed": 0,
                "unchanged": 0,
                "tolerated": 0,
                "unknown": 1,
                "errors": 1,
            },
        )
    ],
    ids=["formats observed unknown and error sources"],
)
def test_given_freshness_result_when_formatting_then_includes_status_groups(
    test_case: FreshnessOutputTestCase,
) -> None:
    text_output: str = format_freshness_text(test_case.result)
    json_output: dict[str, object] = json.loads(format_freshness_json(test_case.result))

    fragment: str
    for fragment in test_case.expected_text_fragments:
        assert fragment in text_output
    assert json_output["summary"] == test_case.expected_summary
