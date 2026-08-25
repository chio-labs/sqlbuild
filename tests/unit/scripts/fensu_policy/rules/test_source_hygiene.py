import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.source_hygiene import reuse_terminology, sqlbuild_comment_policy
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


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
            description="target reuse source relation faults per line",
            path="src/sqlbuild/compiler/planner/_helpers/direct_reuse_example.py",
            source=(
                "def build_origin() -> str:\n"
                "    source_relation = 'prod.orders'\n"
                "    return source_relation\n"
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="dbt reuse source relation faults per line",
            path="src/sqlbuild/integrations/dbt/_helpers/reuse_candidates.py",
            source=(
                "def build_origin() -> str:\n"
                "    source_relation = 'prod.orders'\n"
                "    return source_relation\n"
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="clone source and target terminology faults per occurrence",
            path="src/sqlbuild/executor/clone/main/example.py",
            source=(
                "def run_clone(source_target_name: str) -> str:\n"
                "    source_connection = source_target_name\n"
                "    return source_connection\n"
            ),
            expected_fault_count=4,
        ),
        CustomRuleTestCase(
            description="target cursor receives duplicate global and reuse faults",
            path="src/sqlbuild/compiler/planner/_helpers/reuse.py",
            source="target_cursor = cursor\n",
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="source target terminology passes in source deferral",
            path="src/sqlbuild/compiler/planner/_helpers/warehouse/source_deferral.py",
            source=(
                "def resolve() -> str:\n"
                "    source_target_name = 'prod'\n"
                "    return source_target_name\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="source connection terminology passes in virtual source logic",
            path="src/sqlbuild/virtual/planner/main/plan.py",
            source=(
                "def resolve(connection: object) -> object:\n"
                "    source_connection = connection\n"
                "    return source_connection\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="source relation terminology passes outside reuse code",
            path="src/sqlbuild/example/main/build.py",
            source="def render(source_relation: str) -> str:\n    return source_relation\n",
            expected_fault_count=0,
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
        CustomRuleTestCase(
            description="parameter mutation directive passes",
            path="src/sqlbuild/compiler/planner/_helpers/build.py",
            source=(
                "def build(values: list[str]) -> None:\n"
                "    values.append('x')  # sc: allow-param-mutation\n"
            ),
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
