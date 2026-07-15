from textwrap import dedent

import pytest
from strata import RuleCase, RuleFile, RuleResult, evaluate_rule

from scripts.strata_policy.rules.adapter_ownership import (
    adapter_method_alias,
    adapter_super_delegation,
)
from tests.unit.scripts.strata_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="BaseAdapter method alias faults",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleAdapter(BaseAdapter):
                    render_identifier = BaseAdapter.render_identifier
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="owned method implementation passes",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleAdapter(BaseAdapter):
                    def render_identifier(self, name: str) -> str:
                        return name
                """
            ),
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_checking_method_alias_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=adapter_method_alias,
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
            description="super delegation from abstract method faults",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleAdapter(BaseAdapter):
                    def render_identifier(self, name: str) -> str:
                        return super().render_identifier(name)
                """
            ),
            expected_fault_count=1,
            files=(
                RuleFile(
                    path="src/sqlbuild/adapter/contract/classes/strict_adapter.py",
                    source=dedent(
                        """
                        from abc import abstractmethod

                        class StrictAdapter:
                            @abstractmethod
                            def render_identifier(self, name: str) -> str: ...
                        """
                    ),
                ),
            ),
        ),
        CustomRuleTestCase(
            description="owned abstract method implementation passes",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleAdapter(BaseAdapter):
                    def render_identifier(self, name: str) -> str:
                        return name
                """
            ),
            expected_fault_count=0,
            files=(
                RuleFile(
                    path="src/sqlbuild/adapter/contract/classes/strict_adapter.py",
                    source=dedent(
                        """
                        from abc import abstractmethod

                        class StrictAdapter:
                            @abstractmethod
                            def render_identifier(self, name: str) -> str: ...
                        """
                    ),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_checking_super_delegation_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=adapter_super_delegation,
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
