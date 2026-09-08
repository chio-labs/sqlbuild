"""Policy rule catalogue selection behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.policy_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.policy_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.policy_engine._helpers.guidance.skills import render_skills
from sqlbuild.policy_engine.main.evaluate import evaluate
from sqlbuild.policy_engine.main.render_rule import format_rule
from sqlbuild.policy_engine.models import (
    PolicyCacheConfig,
    PolicyConfig,
    PolicyResult,
    PolicyRule,
    SqlTestPolicyConfig,
    ThresholdOverride,
)
from tests.unit.src.sqlbuild.policy_engine._helpers.engine._test_types import (
    PolicyGuidanceTestCase,
    PolicySelectionTestCase,
    SqlTestPolicyGuidanceTestCase,
)
from tests.unit.src.sqlbuild.policy_engine.main.evaluate.helpers import build_project

BUILT_IN_CODES: tuple[str, ...] = (
    "SQBPC101",
    "SQBPC102",
    "SQBPC103",
    "SQBPC104",
    "SQBPD101",
    "SQBPD102",
    "SQBPD201",
    "SQBPD301",
    "SQBPD302",
    "SQBPD303",
    "SQBPD304",
    "SQBPD305",
    "SQBPD306",
    "SQBPG101",
    "SQBPG102",
    "SQBPR101",
    "SQBPR102",
    "SQBPR103",
    "SQBPR104",
    "SQBPR201",
    "SQBPR202",
    "SQBPR203",
    "SQBPR204",
    "SQBPS101",
    "SQBPS102",
    "SQBPS103",
    "SQBPT101",
    "SQBPT102",
    "SQBPT103",
    "SQBPT104",
    "SQBPT105",
    "SQBPT201",
    "SQBPT202",
    "SQBPT301",
)
STRUCTURE_CODES: tuple[str, ...] = (
    "SQBPS101",
    "SQBPS102",
    "SQBPS103",
)
SQL_TEST_CODES: tuple[str, ...] = (
    "SQBPT101",
    "SQBPT102",
    "SQBPT103",
    "SQBPT104",
    "SQBPT105",
    "SQBPT201",
    "SQBPT202",
    "SQBPT301",
)
NON_STRUCTURE_CODES: tuple[str, ...] = (
    "SQBPC101",
    "SQBPC102",
    "SQBPC103",
    "SQBPC104",
    "SQBPD101",
    "SQBPD102",
    "SQBPD201",
    "SQBPD301",
    "SQBPD302",
    "SQBPD303",
    "SQBPD304",
    "SQBPD305",
    "SQBPD306",
    "SQBPG101",
    "SQBPG102",
    "SQBPR101",
    "SQBPR102",
    "SQBPR103",
    "SQBPR104",
    "SQBPR201",
    "SQBPR202",
    "SQBPR203",
    "SQBPR204",
    *SQL_TEST_CODES,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PolicySelectionTestCase(
            description="built-in namespace activates every built-in",
            select=("SQBP",),
            ignore=(),
            expected_codes=BUILT_IN_CODES,
        ),
        PolicySelectionTestCase(
            description="built-in family activates every family rule",
            select=("SQBPS",),
            ignore=(),
            expected_codes=STRUCTURE_CODES,
        ),
        PolicySelectionTestCase(
            description="exact built-in code activates one rule",
            select=("SQBPS101",),
            ignore=(),
            expected_codes=("SQBPS101",),
        ),
        PolicySelectionTestCase(
            description="SQL test family activates every SQL test policy rule",
            select=("SQBPT",),
            ignore=(),
            expected_codes=SQL_TEST_CODES,
        ),
        PolicySelectionTestCase(
            description="empty selection activates no rules",
            select=(),
            ignore=(),
            expected_codes=(),
        ),
        PolicySelectionTestCase(
            description="ignored family is removed from selected namespace",
            select=("SQBP",),
            ignore=("SQBPS",),
            expected_codes=NON_STRUCTURE_CODES,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rule_selectors_when_resolving_then_returns_expected_codes(
    tmp_path: Path,
    test_case: PolicySelectionTestCase,
) -> None:
    config: PolicyConfig = PolicyConfig(select=test_case.select, ignore=test_case.ignore)
    catalogue: tuple[PolicyRule, ...] = build_catalogue(config=config, project_dir=tmp_path)

    selected: tuple[PolicyRule, ...] = select_rules(
        catalogue=catalogue, config=config, project_dir=tmp_path
    )

    assert tuple(rule.code for rule in selected) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestPolicyGuidanceTestCase(
            description="nested pipeline directory",
            pipeline_directory="chains/commerce",
            expected_path="tests/unit/chains/commerce/",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_test_policy_when_inspecting_and_rendering_skills_then_effective_paths_match(
    tmp_path: Path,
    test_case: SqlTestPolicyGuidanceTestCase,
) -> None:
    config: PolicyConfig = PolicyConfig(
        select=("SQBPT",),
        sql_tests=SqlTestPolicyConfig(pipeline_directory=test_case.pipeline_directory),
    )
    catalogue: tuple[PolicyRule, ...] = build_catalogue(config=config, project_dir=tmp_path)
    rules_by_code: dict[str, PolicyRule] = {item.code: item for item in catalogue}
    rule: PolicyRule = rules_by_code["SQBPT103"]

    inspection: str = format_rule(rule=rule, config=config)
    skill, _ = render_skills(config=config, project_dir=tmp_path)

    assert test_case.expected_path in inspection
    assert test_case.expected_path in skill


@pytest.mark.parametrize(
    "test_case",
    (
        PolicyGuidanceTestCase(
            description="minimum test guidance is identical across remediation inspection and skills",
            expected_snippets=(
                "TEST();",
                "__ref__upstream_model AS",
                "__expected__example_model AS",
                "Do not merely assert that inputs survive unchanged",
                "temporarily perturb the model logic or expected value",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_minimum_test_rule_when_rendering_guidance_then_all_surfaces_have_exact_parity(
    tmp_path: Path,
    test_case: PolicyGuidanceTestCase,
) -> None:
    override: ThresholdOverride = ThresholdOverride(
        paths=("models/mart/**",),
        thresholds={"min_tests_per_model": 2},
        reason="marts require two focused tests",
    )
    config: PolicyConfig = PolicyConfig(
        select=("SQBPT202",),
        threshold_overrides=(override,),
        cache=PolicyCacheConfig(enabled=False),
    )
    catalogue: tuple[PolicyRule, ...] = build_catalogue(config=config, project_dir=tmp_path)
    rules_by_code: dict[str, PolicyRule] = {item.code: item for item in catalogue}
    rule: PolicyRule = rules_by_code["SQBPT202"]
    result: PolicyResult = evaluate(
        project=build_project(
            name="commerce__mart__orders",
            relative_path="models/mart/commerce__mart__orders.sql",
            sql="SELECT id + 1 AS id FROM orders",
            config_values={"materialized": "table"},
        ),
        config=config,
        project_dir=tmp_path,
    )
    inspection: str = format_rule(rule=rule, config=config)
    skill, _ = render_skills(config=config, project_dir=tmp_path)
    without_override: str = resolve_ruleset(
        config=PolicyConfig(select=("SQBPT202",)), project_dir=tmp_path
    ).fingerprint
    with_override: str = resolve_ruleset(config=config, project_dir=tmp_path).fingerprint

    assert result.faults[0].remediation == rule.remediation
    assert f"Remediation: {rule.remediation}" in inspection
    assert f"Remediation: {rule.remediation}" in skill
    assert "marts require two focused tests" in inspection
    assert "marts require two focused tests" in skill
    assert without_override != with_override
    for snippet in test_case.expected_snippets:
        assert snippet in result.faults[0].remediation
