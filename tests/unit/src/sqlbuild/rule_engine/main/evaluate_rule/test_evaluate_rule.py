"""Public custom-rule harness behavior tests."""

import inspect
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.rule_engine.main._evaluate import evaluate
from sqlbuild.rule_engine.models import RulesCacheConfig, RulesConfig, RulesResult
from sqlbuild.rule_engine.types import RuleOptionValue
from sqlbuild.rules.testing import RuleCase, RuleResult, evaluate_rule
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project
from tests.unit.src.sqlbuild.rule_engine.main.evaluate_rule._test_types import (
    EvaluateRuleParityTestCase,
    EvaluateRuleTestCase,
)
from tests.unit.src.sqlbuild.rule_engine.main.evaluate_rule.helpers import required_domain


@pytest.mark.parametrize(
    "test_case",
    [
        EvaluateRuleTestCase(
            description="wrong configured domain faults through real pipeline",
            rule_case=RuleCase(
                description="wrong configured domain faults",
                source=(
                    "MODEL (materialized table);\n\n"
                    "WITH final AS (SELECT 1 AS id)\n"
                    "SELECT id FROM final\n"
                ),
                path="models/mart/commerce__mart__orders.sql",
                config={"required_domain": "support"},
                expected_finding_count=1,
            ),
            expected_code="XSQBRD001",
            expected_path="models/mart/commerce__mart__orders.sql",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_case_when_evaluating_then_runs_real_pipeline(
    test_case: EvaluateRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(rule=required_domain, test_case=test_case.rule_case)

    assert result.finding_count == 1
    assert result.findings[0].code == test_case.expected_code
    assert result.findings[0].path.as_posix() == test_case.expected_path


@pytest.mark.parametrize(
    "test_case",
    (
        EvaluateRuleParityTestCase(
            description="public and native custom paths return deterministic full fault parity",
            rule_case=RuleCase(
                description="wrong configured domain faults",
                source=(
                    "MODEL (materialized table);\n\n"
                    "WITH final AS (SELECT 1 AS id)\n"
                    "SELECT id FROM final\n"
                ),
                path="models/mart/commerce__mart__orders.sql",
                config={"required_domain": "support"},
                expected_finding_count=1,
            ),
            expected_finding_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_same_custom_rule_when_using_public_and_native_paths_then_faults_have_full_parity(
    tmp_path: Path,
    test_case: EvaluateRuleParityTestCase,
) -> None:
    rule_case: RuleCase = test_case.rule_case
    public_result: RuleResult = evaluate_rule(rule=required_domain, test_case=rule_case)
    project: CompiledProject = build_project(
        name="commerce__mart__orders",
        relative_path=rule_case.path,
        sql="WITH final AS (SELECT 1 AS id) SELECT id FROM final",
        authored_sql=rule_case.source,
        config_values={"materialized": "table"},
    )
    source_file: str | None = inspect.getsourcefile(required_domain)
    assert source_file is not None
    rule_path: Path = tmp_path / "rules" / "custom.py"
    rule_path.parent.mkdir(parents=True)
    rule_path.write_text(Path(source_file).read_text(encoding="utf-8"), encoding="utf-8")
    config: RulesConfig = RulesConfig(
        select=("XSQBRD001",),
        thresholds={MIN_CUSTOM_RULE_TEST_CASES: 0},
        rule_options={
            "XSQBRD001": cast("dict[str, RuleOptionValue]", rule_case.config),
        },
        cache=RulesCacheConfig(enabled=False),
    )

    native_result: RulesResult = evaluate(
        project=project,
        config=config,
        project_dir=tmp_path,
    )
    repeated_native_result: RulesResult = evaluate(
        project=project,
        config=config,
        project_dir=tmp_path,
    )

    assert len(native_result.findings) == test_case.expected_finding_count
    assert native_result.findings == public_result.findings
    assert repeated_native_result.findings == native_result.findings
    assert native_result.findings[0] == public_result.findings[0]
