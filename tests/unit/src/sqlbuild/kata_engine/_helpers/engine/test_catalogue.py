"""Kata rule catalogue selection behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.kata_engine._helpers.engine.ruleset import resolve_ruleset
from sqlbuild.kata_engine._helpers.guidance.skills import render_skills
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.main.render_rule import format_rule
from sqlbuild.kata_engine.models import (
    KataCacheConfig,
    KataConfig,
    KataResult,
    KataRule,
    SqlTestPolicyConfig,
    ThresholdOverride,
)
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    KataGuidanceTestCase,
    KataSelectionTestCase,
    SqlTestPolicyGuidanceTestCase,
)
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project

BUILT_IN_CODES: tuple[str, ...] = (
    "SQBKH001",
    "SQBKH002",
    "SQBKH101",
    "SQBKH201",
    "SQBKH301",
    "SQBKH302",
    "SQBKH303",
    "SQBKH304",
    "SQBKH305",
    "SQBKJ001",
    "SQBKJ002",
    "SQBKJ101",
    "SQBKL001",
    "SQBKL101",
    "SQBKN001",
    "SQBKN002",
    "SQBKN003",
    "SQBKR001",
    "SQBKR002",
    "SQBKR201",
    "SQBKR301",
    "SQBKR401",
    "SQBKR500",
    "SQBKR501",
    "SQBKR502",
    "SQBKR503",
    "SQBKS000",
    "SQBKS001",
    "SQBKS002",
    "SQBKS101",
    "SQBKS201",
    "SQBKS202",
    "SQBKS301",
    "SQBKS302",
    "SQBKS401",
    "SQBKS501",
    "SQBKT001",
    "SQBKT002",
    "SQBKT003",
    "SQBKT004",
    "SQBKT101",
    "SQBKX001",
    "SQBKX002",
    "SQBKX201",
)
STRUCTURE_CODES: tuple[str, ...] = (
    "SQBKS000",
    "SQBKS001",
    "SQBKS002",
    "SQBKS101",
    "SQBKS201",
    "SQBKS202",
    "SQBKS301",
    "SQBKS302",
    "SQBKS401",
    "SQBKS501",
)
SQL_TEST_CODES: tuple[str, ...] = (
    "SQBKT001",
    "SQBKT002",
    "SQBKT003",
    "SQBKT004",
    "SQBKT101",
)
NON_STRUCTURE_CODES: tuple[str, ...] = (
    "SQBKH001",
    "SQBKH002",
    "SQBKH101",
    "SQBKH201",
    "SQBKH301",
    "SQBKH302",
    "SQBKH303",
    "SQBKH304",
    "SQBKH305",
    "SQBKJ001",
    "SQBKJ002",
    "SQBKJ101",
    "SQBKL001",
    "SQBKL101",
    "SQBKN001",
    "SQBKN002",
    "SQBKN003",
    "SQBKR001",
    "SQBKR002",
    "SQBKR201",
    "SQBKR301",
    "SQBKR401",
    "SQBKR500",
    "SQBKR501",
    "SQBKR502",
    "SQBKR503",
    *SQL_TEST_CODES,
    "SQBKX001",
    "SQBKX002",
    "SQBKX201",
)


@pytest.mark.parametrize(
    "test_case",
    (
        KataSelectionTestCase(
            description="built-in namespace activates every built-in",
            select=("SQBK",),
            ignore=(),
            expected_codes=BUILT_IN_CODES,
        ),
        KataSelectionTestCase(
            description="built-in family activates every family rule",
            select=("SQBKS",),
            ignore=(),
            expected_codes=STRUCTURE_CODES,
        ),
        KataSelectionTestCase(
            description="exact built-in code activates one rule",
            select=("SQBKS001",),
            ignore=(),
            expected_codes=("SQBKS001",),
        ),
        KataSelectionTestCase(
            description="SQL test family activates every SQL test policy rule",
            select=("SQBKT",),
            ignore=(),
            expected_codes=SQL_TEST_CODES,
        ),
        KataSelectionTestCase(
            description="empty selection activates no rules",
            select=(),
            ignore=(),
            expected_codes=(),
        ),
        KataSelectionTestCase(
            description="ignored family is removed from selected namespace",
            select=("SQBK",),
            ignore=("SQBKS",),
            expected_codes=NON_STRUCTURE_CODES,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rule_selectors_when_resolving_then_returns_expected_codes(
    tmp_path: Path,
    test_case: KataSelectionTestCase,
) -> None:
    config: KataConfig = KataConfig(select=test_case.select, ignore=test_case.ignore)
    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=tmp_path)

    selected: tuple[KataRule, ...] = select_rules(
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
    config: KataConfig = KataConfig(
        select=("SQBKT",),
        sql_tests=SqlTestPolicyConfig(pipeline_directory=test_case.pipeline_directory),
    )
    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=tmp_path)
    rules_by_code: dict[str, KataRule] = {item.code: item for item in catalogue}
    rule: KataRule = rules_by_code["SQBKT003"]

    inspection: str = format_rule(rule=rule, config=config)
    skill, _ = render_skills(config=config, project_dir=tmp_path)

    assert test_case.expected_path in inspection
    assert test_case.expected_path in skill


@pytest.mark.parametrize(
    "test_case",
    (
        KataGuidanceTestCase(
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
    test_case: KataGuidanceTestCase,
) -> None:
    override: ThresholdOverride = ThresholdOverride(
        paths=("models/mart/**",),
        thresholds={"min_tests_per_model": 2},
        reason="marts require two focused tests",
    )
    config: KataConfig = KataConfig(
        select=("SQBKX002",),
        threshold_overrides=(override,),
        cache=KataCacheConfig(enabled=False),
    )
    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=tmp_path)
    rules_by_code: dict[str, KataRule] = {item.code: item for item in catalogue}
    rule: KataRule = rules_by_code["SQBKX002"]
    result: KataResult = evaluate(
        project=build_project(
            name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT id + 1 AS id FROM prices",
            config_values={"materialized": "table"},
        ),
        config=config,
        project_dir=tmp_path,
    )
    inspection: str = format_rule(rule=rule, config=config)
    skill, _ = render_skills(config=config, project_dir=tmp_path)
    without_override: str = resolve_ruleset(
        config=KataConfig(select=("SQBKX002",)), project_dir=tmp_path
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
