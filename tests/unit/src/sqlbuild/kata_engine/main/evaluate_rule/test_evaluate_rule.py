"""Public custom-rule harness behavior tests."""

import inspect
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata import RuleCase, RuleResult, evaluate_rule
from sqlbuild.kata_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataCacheConfig, KataConfig, KataResult
from sqlbuild.kata_engine.types import RuleOptionValue
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project
from tests.unit.src.sqlbuild.kata_engine.main.evaluate_rule._test_types import (
    EvaluateRuleParityTestCase,
    EvaluateRuleTestCase,
)
from tests.unit.src.sqlbuild.kata_engine.main.evaluate_rule.helpers import required_domain


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
                path="models/mart/market__mart__prices.sql",
                config={"required_domain": "race"},
                expected_fault_count=1,
            ),
            expected_code="XSQBKD001",
            expected_path="models/mart/market__mart__prices.sql",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_case_when_evaluating_then_runs_real_pipeline(
    test_case: EvaluateRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(rule=required_domain, test_case=test_case.rule_case)

    assert result.fault_count == 1
    assert result.faults[0].code == test_case.expected_code
    assert result.faults[0].path.as_posix() == test_case.expected_path


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
                path="models/mart/market__mart__prices.sql",
                config={"required_domain": "race"},
                expected_fault_count=1,
            ),
            expected_fault_count=1,
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
        name="market__mart__prices",
        relative_path=rule_case.path,
        sql="WITH final AS (SELECT 1 AS id) SELECT id FROM final",
        authored_sql=rule_case.source,
        config_values={"materialized": "table"},
    )
    source_file: str | None = inspect.getsourcefile(required_domain)
    assert source_file is not None
    rule_path: Path = tmp_path / "kata" / "rules" / "custom.py"
    rule_path.parent.mkdir(parents=True)
    rule_path.write_text(Path(source_file).read_text(encoding="utf-8"), encoding="utf-8")
    config: KataConfig = KataConfig(
        select=("XSQBKD001",),
        thresholds={MIN_CUSTOM_RULE_TEST_CASES: 0},
        rule_options={
            "XSQBKD001": cast("dict[str, RuleOptionValue]", rule_case.config),
        },
        rule_paths=("kata/rules/custom.py",),
        cache=KataCacheConfig(enabled=False),
    )

    native_result: KataResult = evaluate(
        project=project,
        config=config,
        project_dir=tmp_path,
    )
    repeated_native_result: KataResult = evaluate(
        project=project,
        config=config,
        project_dir=tmp_path,
    )

    assert len(native_result.faults) == test_case.expected_fault_count
    assert native_result.faults == public_result.faults
    assert repeated_native_result.faults == native_result.faults
    assert native_result.faults[0] == public_result.faults[0]
