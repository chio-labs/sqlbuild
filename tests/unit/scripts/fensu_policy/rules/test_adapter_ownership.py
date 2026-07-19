from textwrap import dedent

import pytest
from fensu import RuleCase, RuleFile, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.adapter_ownership import (
    adapter_method_alias,
    adapter_super_delegation,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


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
        CustomRuleTestCase(
            description="registered built-in adapter alias faults",
            path="src/sqlbuild/adapters/foo/classes/foo_adapter.py",
            source=dedent(
                """
                class FooAdapter(BaseAdapter):
                    render_identifier = BaseAdapter.render_identifier
                """
            ),
            expected_fault_count=1,
            files=(
                RuleFile(
                    path="src/sqlbuild/adapter/discovery/main/builtins.py",
                    source=dedent(
                        """
                        def builtin_adapter_classes():
                            from sqlbuild.adapters.foo.classes.foo_adapter import FooAdapter

                            return {"foo": FooAdapter}
                        """
                    ),
                ),
            ),
        ),
        CustomRuleTestCase(
            description="unregistered adapter class alias passes",
            path="src/sqlbuild/adapters/foo/classes/foo_adapter.py",
            source=dedent(
                """
                class FooAdapter(BaseAdapter):
                    render_identifier = BaseAdapter.render_identifier
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
        CustomRuleTestCase(
            description="qualified abstract decorator preserves super fault",
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
                        import abc

                        class StrictAdapter:
                            @abc.abstractmethod
                            def render_identifier(self, name: str) -> str: ...
                        """
                    ),
                ),
            ),
        ),
        CustomRuleTestCase(
            description="aliased abstract decorator preserves super fault",
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
                        from abc import abstractmethod as abstract

                        class StrictAdapter:
                            @abstract
                            def render_identifier(self, name: str) -> str: ...
                        """
                    ),
                ),
            ),
        ),
        CustomRuleTestCase(
            description="unrelated abstract contract method does not fault",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleAdapter(BaseAdapter):
                    def cleanup(self) -> None:
                        super().cleanup()
                """
            ),
            expected_fault_count=0,
            files=(
                RuleFile(
                    path="src/sqlbuild/adapter/contract/classes/strict_adapter.py",
                    source="class StrictAdapter:\n    pass\n",
                ),
                RuleFile(
                    path="src/sqlbuild/adapter/contract/classes/unrelated.py",
                    source=dedent(
                        """
                        from abc import abstractmethod

                        class Unrelated:
                            @abstractmethod
                            def cleanup(self) -> None: ...
                        """
                    ),
                ),
            ),
        ),
        CustomRuleTestCase(
            description="registered built-in super delegation faults",
            path="src/sqlbuild/adapters/foo/classes/foo_adapter.py",
            source=dedent(
                """
                class FooAdapter(BaseAdapter):
                    def render_identifier(self, name: str) -> str:
                        return super().render_identifier(name)
                """
            ),
            expected_fault_count=1,
            files=(
                RuleFile(
                    path="src/sqlbuild/adapter/discovery/main/builtins.py",
                    source=dedent(
                        """
                        def builtin_adapter_classes():
                            from sqlbuild.adapters.foo.classes.foo_adapter import FooAdapter

                            return {"foo": FooAdapter}
                        """
                    ),
                ),
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
