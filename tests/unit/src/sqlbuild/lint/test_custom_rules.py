"""Public custom SQL lint authoring API tests."""

import pytest

from sqlbuild.lint import CustomLintFinding, evaluate_lint_rule
from tests.unit.src.sqlbuild.lint._helpers.helpers import no_star
from tests.unit.src.sqlbuild.lint._test_types import CustomLintTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomLintTestCase(
            description="plain SQL exposes no project state",
            source="SELECT * FROM items",
            expected_code="XSQBLS001",
            expected_start=7,
            expected_end=8,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_plain_sql_when_evaluating_custom_lint_then_project_state_is_unavailable(
    test_case: CustomLintTestCase,
) -> None:
    findings: tuple[CustomLintFinding, ...] = evaluate_lint_rule(
        rule=no_star, source=test_case.source
    )

    assert len(findings) == 1
    assert findings[0].code == test_case.expected_code
    assert findings[0].start == test_case.expected_start
    assert findings[0].end == test_case.expected_end
