from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands._helpers.freshness.output import (
    format_freshness_json,
    format_freshness_text,
)
from sqlbuild.cli.commands.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.cli.commands.types import FreshnessSourceStatus
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.freshness._test_types import (
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
                        age_status=SourceFreshnessAgeStatus.WARN,
                    ),
                    FreshnessSourceResult(
                        name="raw_clicks",
                        status=FreshnessSourceStatus.OBSERVED,
                        strategy="timestamp",
                        value_kind="timestamp",
                        current_data_version="2026-01-01T00:30:00",
                        age_status=SourceFreshnessAgeStatus.PASS,
                    ),
                    FreshnessSourceResult(
                        name="raw_shipments",
                        status=FreshnessSourceStatus.OBSERVED,
                        strategy="timestamp",
                        value_kind="timestamp",
                        current_data_version="2025-12-31T20:00:00",
                        age_status=SourceFreshnessAgeStatus.ERROR,
                    ),
                    FreshnessSourceResult(
                        name="raw_inventory",
                        status=FreshnessSourceStatus.OBSERVED,
                        strategy="integer",
                        value_kind="integer",
                        current_data_version="42",
                        age_status=SourceFreshnessAgeStatus.UNKNOWN,
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
                "Observed (4)",
                "raw_orders  timestamp  2026-01-01T00:00:00  timestamp  tolerance 15m  age warn",
                "raw_clicks  timestamp  2026-01-01T00:30:00  timestamp  age pass",
                "raw_shipments  timestamp  2025-12-31T20:00:00  timestamp  age error",
                "raw_inventory  integer  42  integer  age unknown",
                "Unknown (1)",
                "raw_payments  no freshness config and adapter metadata unavailable",
                "Errors (1)",
                "raw_events  freshness query failed",
                "Summary: observed=4 changed=0 unchanged=0 tolerated=0 unknown=1 errors=1",
                "Age policy: pass=1 warn=1 error=1 unknown=1",
            ),
            expected_summary={
                "observed": 4,
                "changed": 0,
                "unchanged": 0,
                "tolerated": 0,
                "unknown": 1,
                "errors": 1,
                "age_pass": 1,
                "age_warn": 1,
                "age_error": 1,
                "age_unknown": 1,
            },
            expected_json_age_statuses={
                "raw_orders": "warn",
                "raw_clicks": "pass",
                "raw_shipments": "error",
                "raw_inventory": "unknown",
                "raw_payments": None,
                "raw_events": None,
            },
        )
    ],
    ids=lambda case: case.description,
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
    sources: list[dict[str, object]] = json_output["sources"]
    assert {str(source["name"]): source["age_status"] for source in sources} == (
        test_case.expected_json_age_statuses
    )
