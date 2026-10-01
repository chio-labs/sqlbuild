from __future__ import annotations

import pytest

from sqlbuild.rule_engine.main.render_rules_progress import format_rules_progress
from sqlbuild.rule_engine.models import RulesRunResult
from tests.unit.src.sqlbuild.rule_engine.main.render_rules_progress._test_types import (
    RulesProgressTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        RulesProgressTestCase(
            description="wall time leads concurrent built-in and custom rule time",
            elapsed_seconds=14.5,
            built_in_ms=5_600,
            custom_ms=13_400,
            expected_message="Evaluated rules. (14.50s; built-in 5.60s, custom 13.40s)",
        ),
        RulesProgressTestCase(
            description="skipped type-proof rules follow the timings when requested",
            elapsed_seconds=0.25,
            built_in_ms=100,
            custom_ms=0,
            skipped_type_proof_rules=("SQBRCONTRACT105",),
            note_skipped_rules=True,
            expected_message=(
                "Evaluated rules. (0.25s; built-in 0.10s, custom 0.00s); skipped type-proof "
                "rules (SQBRCONTRACT105) because SQL analysis is disabled"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rules_run_when_formatting_progress_then_reports_phase_wall_time_first(
    test_case: RulesProgressTestCase,
) -> None:
    result: RulesRunResult = RulesRunResult(
        findings=(),
        evaluated_models=0,
        built_in_ms=test_case.built_in_ms,
        custom_ms=test_case.custom_ms,
        skipped_type_proof_rules=test_case.skipped_type_proof_rules,
    )

    message: str = format_rules_progress(
        elapsed_seconds=test_case.elapsed_seconds,
        result=result,
        note_skipped_rules=test_case.note_skipped_rules,
    )

    assert message == test_case.expected_message
