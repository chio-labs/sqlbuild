from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.module_boundaries import (
    adapter_entry_class_count,
    adapter_entry_content,
    client_entry_filename,
    client_module_content,
    client_public_class_count,
    dev_tooling_location,
    main_support_placement,
    provider_public_surface,
    sqlbuild_generic_filename,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="runtime check module faults",
            path="src/sqlbuild/example/main/check_example.py",
            source="def check_example() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="runtime behavior module passes",
            path="src/sqlbuild/example/main/build_example.py",
            source="def build_example() -> None:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_dev_tooling_location_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=dev_tooling_location,
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
            description="base module faults",
            path="src/sqlbuild/example/main/base.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="common module faults",
            path="src/sqlbuild/example/main/common.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="helpers module faults",
            path="src/sqlbuild/example/helpers.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="adapter-local helpers module faults",
            path="src/sqlbuild/adapters/clickhouse/helpers.py",
            source="def render_clickhouse_sql() -> str:\n    return 'SELECT 1'\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="domain module passes",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_when_checking_generic_filename_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=sqlbuild_generic_filename,
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
            description="adapter main module faults",
            path="src/sqlbuild/adapters/example/main.py",
            source="class ExampleClient:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="adapter client module passes",
            path="src/sqlbuild/adapters/example/client.py",
            source="class ExampleClient:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_client_module_when_checking_filename_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=client_entry_filename,
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
            description="multiple public client classes fault",
            path="src/sqlbuild/adapters/example/client.py",
            source="class ExampleClient:\n    pass\n\nclass BackupClient:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="one public client class passes",
            path="src/sqlbuild/adapters/example/client.py",
            source="class ExampleClient:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_client_module_when_checking_class_count_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=client_public_class_count,
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
            description="client function faults",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                class ExampleClient:
                    pass

                def build_client() -> ExampleClient:
                    return ExampleClient()
                """
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="client imports and class methods pass",
            path="src/sqlbuild/adapters/example/client.py",
            source=dedent(
                """
                from sqlbuild.adapters.example.models import ExampleConfig

                class ExampleClient:
                    @classmethod
                    def from_config(cls, config: ExampleConfig) -> "ExampleClient":
                        return cls()
                """
            ),
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_client_module_when_checking_content_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=client_module_content,
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
            description="multiple adapter entry classes fault",
            path="src/sqlbuild/adapter/example/backend/entry.py",
            source="class ExampleAdapter:\n    pass\n\nclass BackupAdapter:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="one adapter entry class passes",
            path="src/sqlbuild/adapter/example/backend/entry.py",
            source="class ExampleAdapter:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_entry_when_checking_class_count_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=adapter_entry_class_count,
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
            description="adapter entry function faults",
            path="src/sqlbuild/adapter/example/backend/entry.py",
            source="class ExampleAdapter:\n    pass\n\ndef build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="adapter entry class-only module passes",
            path="src/sqlbuild/adapter/example/backend/entry.py",
            source="class ExampleAdapter:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_entry_when_checking_content_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=adapter_entry_content,
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
            description="provider module function faults",
            path="src/sqlbuild/providers.py",
            source="class Provider:\n    pass\n\ndef build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="single Provider class passes",
            path="src/sqlbuild/providers.py",
            source="class Provider:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_provider_module_when_checking_surface_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=provider_public_surface,
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
            description="support package below main faults",
            path="src/sqlbuild/example/main/_helpers/build.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="shared package below main faults",
            path="src/sqlbuild/example/main/shared/__init__.py",
            source="",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="CLI shared package below main faults",
            path="src/sqlbuild/cli/commands/main/shared/__init__.py",
            source="",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="tooling support package below main faults",
            path="scripts/example/main/_helpers/build.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=1,
            scope="tooling",
            scope_root="scripts",
        ),
        CustomRuleTestCase(
            description="flat main entry passes",
            path="src/sqlbuild/example/main/build.py",
            source="def build() -> None:\n    pass\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_main_module_when_checking_support_placement_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=main_support_placement,
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
