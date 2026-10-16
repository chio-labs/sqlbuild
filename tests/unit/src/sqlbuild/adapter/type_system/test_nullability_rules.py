import pytest

from sqlbuild._native import InferredNullability
from sqlbuild.adapter.type_system.main.conditional_result_nullability import (
    conditional_result_nullability,
)
from sqlbuild.adapter.type_system.main.first_arg_nullability import first_arg_nullability
from sqlbuild.adapter.type_system.main.safe_cast_nullability import safe_cast_nullability
from tests.unit.src.sqlbuild.adapter.type_system._test_types import (
    FirstArgIdentityTestCase,
    NullabilityRuleTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NullabilityRuleTestCase(
            description="no arguments",
            args=(),
            expected_first_arg=InferredNullability.UNKNOWN,
            expected_conditional=InferredNullability.UNKNOWN,
            expected_safe_cast=InferredNullability.UNKNOWN,
        ),
        NullabilityRuleTestCase(
            description="two non-null results",
            args=(
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            ),
            expected_first_arg=InferredNullability.UNKNOWN,
            expected_conditional=InferredNullability.NON_NULL,
            expected_safe_cast=InferredNullability.UNKNOWN,
        ),
        NullabilityRuleTestCase(
            description="one nullable result",
            args=(
                InferredNullability.NULLABLE,
                InferredNullability.NON_NULL,
                InferredNullability.NULLABLE,
            ),
            expected_first_arg=InferredNullability.NULLABLE,
            expected_conditional=InferredNullability.NULLABLE,
            expected_safe_cast=InferredNullability.NULLABLE,
        ),
        NullabilityRuleTestCase(
            description="an unproven result",
            args=(
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
                InferredNullability.UNKNOWN,
            ),
            expected_first_arg=InferredNullability.NON_NULL,
            expected_conditional=InferredNullability.UNKNOWN,
            expected_safe_cast=InferredNullability.UNKNOWN,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_argument_nullabilities_when_inferred_then_each_public_rule_returns_its_member(
    test_case: NullabilityRuleTestCase,
) -> None:
    assert first_arg_nullability(test_case.args) is test_case.expected_first_arg
    assert conditional_result_nullability(test_case.args) is test_case.expected_conditional
    assert safe_cast_nullability(test_case.args) is test_case.expected_safe_cast


@pytest.mark.parametrize(
    "test_case",
    [
        FirstArgIdentityTestCase(
            description="plain text", argument="nullable", expected_same_object=True
        ),
        FirstArgIdentityTestCase(
            description="an enum member",
            argument=InferredNullability.NON_NULL,
            expected_same_object=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_first_argument_when_first_arg_inferred_then_the_argument_itself_returns(
    test_case: FirstArgIdentityTestCase,
) -> None:
    returned: object = first_arg_nullability((test_case.argument,))  # ty: ignore[invalid-argument-type]

    assert (returned is test_case.argument) is test_case.expected_same_object


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
