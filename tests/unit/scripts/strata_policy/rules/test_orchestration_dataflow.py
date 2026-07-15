from textwrap import dedent

import pytest
from strata import RuleCase, RuleResult, evaluate_rule

from scripts.strata_policy.rules.orchestration_dataflow import (
    main_discarded_call,
    metadata_query_loop,
    phase_parameter_mutation,
)
from tests.unit.scripts.strata_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="metadata query in loop faults",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                def collect(adapter, names):
                    for name in names:
                        adapter.relation_exists(name=name)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="metadata query before loop passes",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                def collect(adapter, names):
                    relations = adapter.list_relations()
                    return [name for name in names if name in relations]
                """
            ),
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_code_when_checking_metadata_loop_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=metadata_query_loop,
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
            description="bare phase call faults",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    build_phase()\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="explicitly discarded phase result passes",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    _ = build_phase()\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_main_code_when_checking_discarded_calls_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=main_discarded_call,
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
            description="compiler helper parameter mutation faults",
            path="src/sqlbuild/compiler/planner/_helpers/build.py",
            source="def build(values: list[str]) -> None:\n    values.append('x')\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="documented builder parameter mutation passes",
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
def test_given_helper_code_when_checking_parameter_mutation_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=phase_parameter_mutation,
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
