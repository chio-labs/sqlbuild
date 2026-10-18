import pytest

from scripts.release_gate._helpers.expressions import evaluate, evaluate_template
from scripts.release_gate.exceptions import ReleaseGateError
from tests.unit.scripts.release_gate._helpers._test_types import (
    ExpressionTestCase,
    TemplateTestCase,
    UnsupportedExpressionTestCase,
)
from tests.unit.scripts.release_gate._helpers.helpers import CONTEXTS


@pytest.mark.parametrize(
    "test_case",
    [
        ExpressionTestCase(
            description="and returns its right operand when the left is truthy",
            expression="github.event_name == 'pull_request' && 'Suites'",
            expected_value="Suites",
        ),
        ExpressionTestCase(
            description="or falls back when the left is falsy",
            expression="github.event_name == 'merge_group' && 'Suites' || 'Verify'",
            expected_value="Verify",
        ),
        ExpressionTestCase(
            description="string comparison ignores case",
            expression="github.event_name == 'Pull_Request'",
            expected_value=True,
        ),
        ExpressionTestCase(
            description="startsWith ignores case",
            expression="startsWith(github.event.pull_request.head.ref, 'release-please--')",
            expected_value=True,
        ),
        ExpressionTestCase(
            description="a missing property is null",
            expression="github.event.merge_group.head_sha",
            expected_value=None,
        ),
        ExpressionTestCase(
            description="negation and grouping",
            expression="!(github.event_name != 'pull_request') && 'yes' || 'no'",
            expected_value="yes",
        ),
        ExpressionTestCase(
            description="quoted apostrophe in a string literal",
            expression="'it''s'",
            expected_value="it's",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expression_when_evaluating_then_returns_github_value(
    test_case: ExpressionTestCase,
) -> None:
    value: object = evaluate(expression=test_case.expression, contexts=CONTEXTS)

    assert value == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        TemplateTestCase(
            description="every expression is substituted",
            template="${{ github.event_name }} on ${{ github.repository }}",
            expected_value="pull_request on example-org/example-project",
        ),
        TemplateTestCase(
            description="null renders empty and booleans render lowercase",
            template="[${{ github.missing }}] ${{ github.event_name == 'pull_request' }}",
            expected_value="[] true",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_template_when_evaluating_then_substitutes_expressions(
    test_case: TemplateTestCase,
) -> None:
    assert evaluate_template(template=test_case.template, contexts=CONTEXTS) == (
        test_case.expected_value
    )


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedExpressionTestCase(
            description="unsupported function",
            expression="contains(github.event_name, 'pull')",
            expected_message="Unsupported function contains",
        ),
        UnsupportedExpressionTestCase(
            description="unsupported operator",
            expression="github.run_attempt > 1",
            expected_message="Unsupported expression syntax",
        ),
        UnsupportedExpressionTestCase(
            description="unbalanced parentheses",
            expression="(github.event_name == 'pull_request'",
            expected_message="Unexpected end of expression",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_expression_when_evaluating_then_raises_gate_error(
    test_case: UnsupportedExpressionTestCase,
) -> None:
    with pytest.raises(ReleaseGateError, match=test_case.expected_message):
        evaluate(expression=test_case.expression, contexts=CONTEXTS)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
