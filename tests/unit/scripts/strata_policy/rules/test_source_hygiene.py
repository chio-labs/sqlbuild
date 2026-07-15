import pytest
from strata import RuleCase, RuleResult, evaluate_rule

from scripts.strata_policy.rules.source_hygiene import reuse_terminology, sqlbuild_comment_policy
from tests.unit.scripts.strata_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="globally ambiguous reuse term faults per line",
            path="src/sqlbuild/example/main/build.py",
            source=(
                "def build() -> str:\n    source_fingerprint = 'x'\n    return source_fingerprint\n"
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="origin terminology passes",
            path="src/sqlbuild/example/main/build.py",
            source="def build(origin_fingerprint: str) -> str:\n    return origin_fingerprint\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_checking_reuse_terminology_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=reuse_terminology,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="explanatory comment faults",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    # explanation\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="type ignore directive passes",
            path="src/sqlbuild/example/main/build.py",
            source="def build(value):\n    return value  # type: ignore[no-any-return]\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_checking_comment_policy_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=sqlbuild_comment_policy,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
