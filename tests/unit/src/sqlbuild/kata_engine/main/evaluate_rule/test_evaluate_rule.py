"""Public custom-rule harness behavior tests."""

import pytest

from sqlbuild.kata import RuleCase, RuleResult, evaluate_rule
from tests.unit.src.sqlbuild.kata_engine.main.evaluate_rule._test_types import (
    EvaluateRuleTestCase,
)
from tests.unit.src.sqlbuild.kata_engine.main.evaluate_rule.helpers import required_domain


@pytest.mark.parametrize(
    "test_case",
    [
        EvaluateRuleTestCase(
            description="wrong configured domain faults through real pipeline",
            rule_case=RuleCase(
                description="wrong configured domain faults",
                source=(
                    "MODEL (materialized table);\n\n"
                    "WITH final AS (SELECT 1 AS id)\n"
                    "SELECT id FROM final\n"
                ),
                path="models/mart/market__mart__prices.sql",
                config={"required_domain": "race"},
                expected_fault_count=1,
            ),
            expected_code="XDOMAIN001",
            expected_path="models/mart/market__mart__prices.sql",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_case_when_evaluating_then_runs_real_pipeline(
    test_case: EvaluateRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(rule=required_domain, test_case=test_case.rule_case)

    assert result.fault_count == 1
    assert result.faults[0].code == test_case.expected_code
    assert result.faults[0].path.as_posix() == test_case.expected_path
