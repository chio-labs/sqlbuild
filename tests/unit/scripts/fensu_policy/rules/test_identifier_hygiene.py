import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.identifier_hygiene import relation_identity_key_must_fold
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="unfolded relation identity key faults",
            path="src/sqlbuild/executor/janitor/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass(frozen=True)\n"
                "class RelationKey:\n"
                "    database: str | None\n"
                "    schema: str | None\n"
                "    name: str\n"
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="identity key declaring normalization passes",
            path="src/sqlbuild/executor/janitor/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass(frozen=True)\n"
                "class RelationKey:\n"
                "    database: str | None\n"
                "    schema: str | None\n"
                "    name: str\n"
                "\n"
                "    def __post_init__(self) -> None:\n"
                "        object.__setattr__(self, 'name', self.name.lower())\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="mutable identity-shaped dataclass is not an identity key",
            path="src/sqlbuild/executor/janitor/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass\n"
                "class RelationKey:\n"
                "    database: str | None\n"
                "    schema: str | None\n"
                "    name: str\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="dataclass carrying extra metadata is not an identity key",
            path="src/sqlbuild/executor/janitor/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass(frozen=True)\n"
                "class RelationInfo:\n"
                "    database: str | None\n"
                "    schema: str | None\n"
                "    name: str\n"
                "    relation_type: str\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="identity-shaped dataclass with field defaults is not an identity key",
            path="src/sqlbuild/integrations/dbt/_helpers/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass(frozen=True)\n"
                "class TargetContext:\n"
                "    name: str\n"
                "    schema: str | None = None\n"
                "    database: str | None = None\n"
            ),
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="adapter modules are exempt from identity key folding policy",
            path="src/sqlbuild/adapter/contract/example.py",
            source=(
                "from dataclasses import dataclass\n"
                "\n"
                "@dataclass(frozen=True)\n"
                "class RelationKey:\n"
                "    database: str | None\n"
                "    schema: str | None\n"
                "    name: str\n"
            ),
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_checking_relation_identity_keys_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=relation_identity_key_must_fold,
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
