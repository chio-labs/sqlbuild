from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.orchestration_dataflow import (
    main_discarded_call,
    metadata_query_loop,
    phase_parameter_mutation,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


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
            description="describe relation in loop faults",
            path="src/sqlbuild/example/main/describe.py",
            source=dedent(
                """
                def describe(adapter, relations):
                    for relation in relations:
                        adapter.describe_relation(relation=relation)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="query column names in loop faults",
            path="src/sqlbuild/example/main/columns.py",
            source=dedent(
                """
                def columns(adapter, expressions):
                    for sql in expressions:
                        adapter.query_column_names(sql=sql)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="schema existence check in loop faults",
            path="src/sqlbuild/example/main/schemas.py",
            source=dedent(
                """
                def schemas(adapter, names):
                    for name in names:
                        adapter.schema_exists(schema=name)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="table freshness metadata in loop faults",
            path="src/sqlbuild/example/main/freshness.py",
            source=dedent(
                """
                def freshness(adapter, names):
                    for name in names:
                        adapter.get_table_freshness_metadata(name=name)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="transitive metadata helper in loop faults",
            path="src/sqlbuild/example/main/indirect.py",
            source=dedent(
                """
                def _exists(adapter, name):
                    return adapter.relation_exists(name=name)

                def _exists_named(adapter, name):
                    return _exists(adapter, name)

                def collect(adapter, names):
                    for name in names:
                        _exists_named(adapter, name)
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="same-named non-metadata helper in comprehension passes",
            path="src/sqlbuild/example/main/unrelated.py",
            source=dedent(
                """
                def _exists(value):
                    return value is not None

                def collect(values):
                    return [value for value in values if _exists(value)]
                """
            ),
            expected_fault_count=0,
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
        CustomRuleTestCase(
            description="approved side-effect names and method calls pass",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                def build(results, stream, backend) -> None:
                    validate_inputs()
                    enforce_policy()
                    check_state()
                    on_progress()
                    report_progress()
                    _report_progress()
                    log_event()
                    print("demo")
                    write_summary(results)
                    _ = build_receipt()
                    results.append("demo")
                    stream.write("demo")
                    backend.close()
                """
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="discarded phase in private main function faults",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                def build() -> None:
                    return _resolve()

                def _resolve() -> None:
                    build_phase()
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="discarded underscore-prefixed phase faults",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    _build_phase()\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="discarded tooling main phase faults",
            path="scripts/example/main/build.py",
            source="def build() -> None:\n    build_phase()\n",
            expected_fault_count=1,
            scope="tooling",
            scope_root="scripts",
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
        CustomRuleTestCase(
            description="methods mutating self pass",
            path="src/sqlbuild/compiler/planner/_helpers/build.py",
            source=dedent(
                """
                class _State:
                    def __init__(self, values: list[str]) -> None:
                        self.values = values

                    def merge(self, extra: list[str]) -> None:
                        self.values.extend(extra)
                """
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
