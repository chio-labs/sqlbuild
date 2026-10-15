import pytest

from sqlbuild._native import CliUserError, enforce_model_execution_limit
from sqlbuild.spec.contracts.models import ExecutionLimitsConfig
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning._test_types import (
    ModelExecutionLimitTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.build_planning.helpers import (
    EXECUTION_LIMIT_BUILD_NOTE,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelExecutionLimitTestCase(
            description="model count equals configured limit",
            model_count=25,
            maximum_models=25,
            expected_code=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_count_within_limit_when_enforcing_then_build_is_allowed(
    test_case: ModelExecutionLimitTestCase,
) -> None:
    result: None = enforce_model_execution_limit(
        model_count=test_case.model_count,
        target_name="dev",
        limits=ExecutionLimitsConfig(max_models=test_case.maximum_models),
        refusal_note=EXECUTION_LIMIT_BUILD_NOTE,
    )
    assert result is test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        ModelExecutionLimitTestCase(
            description="model count exceeds configured limit",
            model_count=26,
            maximum_models=25,
            remediation=(
                "Review the expanded selection and request approval before changing the policy."
            ),
            expected_code="C413",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_count_above_limit_when_enforcing_then_error_has_custom_remediation(
    test_case: ModelExecutionLimitTestCase,
) -> None:

    with pytest.raises(CliUserError) as raised:
        enforce_model_execution_limit(
            model_count=test_case.model_count,
            target_name="dev",
            limits=ExecutionLimitsConfig(
                max_models=test_case.maximum_models,
                remediation=test_case.remediation,
            ),
            refusal_note=EXECUTION_LIMIT_BUILD_NOTE,
        )

    assert raised.value.code == test_case.expected_code
    assert raised.value.help == test_case.remediation
    assert "Selected models: 26" in raised.value.message
    assert "Maximum models:  25" in raised.value.message
    assert "No warehouse changes were made." in raised.value.message
