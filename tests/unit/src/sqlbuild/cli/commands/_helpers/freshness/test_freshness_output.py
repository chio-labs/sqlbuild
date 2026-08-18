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
                "├── raw_orders",
                "value 2026-01-01T00:00:00  kind timestamp  via timestamp  tolerance 15m  age warn",
                "value 2026-01-01T00:30:00  kind timestamp  via timestamp  age pass",
                "value 2025-12-31T20:00:00  kind timestamp  via timestamp  age error",
                "└── raw_inventory",
                "value 42  kind integer  via integer  age unknown",
                "Unknown (1)",
                "└── raw_payments",
                "no freshness config and adapter metadata unavailable",
                "Errors (1)",
                "└── raw_events",
                "freshness query failed",
                "OBSERVED=4  CHANGED=0  UNCHANGED=0  TOLERATED=0  UNKNOWN=1  ERROR=1",
                "Age policy  PASS=1  WARN=1  ERROR=1  UNKNOWN=1",
            ),
            expected_color_fragments=(
                "\033[34m\033[1mSource freshness\033[0m",
                "\033[33mage warn\033[0m",
                "\033[32mage pass\033[0m",
                "\033[38;5;167mage error\033[0m",
                "\033[33mno freshness config and adapter metadata unavailable\033[0m",
                "\033[38;5;167mfreshness query failed\033[0m",
                "\033[2mUNKNOWN=\033[0m\033[33m1\033[0m",
                "\033[2mERROR=\033[0m\033[38;5;167m1\033[0m",
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
    text_output: str = format_freshness_text(result=test_case.result)
    color_text_output: str = format_freshness_text(result=test_case.result, use_color=True)
    json_output: dict[str, object] = json.loads(format_freshness_json(test_case.result))

    fragment: str
    for fragment in test_case.expected_text_fragments:
        assert fragment in text_output
    for fragment in test_case.expected_color_fragments:
        assert fragment in color_text_output
    assert json_output["summary"] == test_case.expected_summary
    sources: list[dict[str, object]] = json_output["sources"]
    assert {str(source["name"]): source["age_status"] for source in sources} == (
        test_case.expected_json_age_statuses
    )
