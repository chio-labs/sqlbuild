"""Custom-rule loading and hermeticity behavior tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.policy_engine.exceptions import PolicyError
from sqlbuild.policy_engine.main.evaluate import evaluate
from sqlbuild.policy_engine.models import (
    PolicyConfig,
    PolicyResult,
    RuleExemption,
    RuleIgnore,
)
from tests.unit.src.sqlbuild.policy_engine._helpers.engine._test_types import (
    CustomRuleSuppressionTestCase,
    CustomRuleTestCase,
)
from tests.unit.src.sqlbuild.policy_engine._helpers.engine.helpers import custom_rule_inputs


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="selected custom rule faults",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            expected_fault_codes=("XSQBPT101",),
            expected_fault_lines=(1,),
        ),
        CustomRuleTestCase(
            description="untested custom rule faults coverage",
            body="del model\n    return []",
            require_cacheable=False,
            expected_fault_codes=("SQBPT301",),
            expected_fault_lines=(4,),
            minimum_custom_rule_cases=1,
        ),
        CustomRuleTestCase(
            description="default-off custom rule is not activated by prefix",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            select=("XSQBPT",),
        ),
        CustomRuleTestCase(
            description="default-enabled custom rule is activated by prefix",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            expected_fault_codes=("XSQBPT101",),
            expected_fault_lines=(1,),
            select=("XSQBPT",),
            enabled_by_default=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selected_custom_rule_when_evaluating_then_reports_fault(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    result: PolicyResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert tuple(fault.code for fault in result.faults) == test_case.expected_fault_codes
    assert tuple(fault.line for fault in result.faults) == test_case.expected_fault_lines


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="custom rule disables cache",
            body="del model\n    return []",
            require_cacheable=False,
            expected_cache_hits=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_rule_without_requirement_when_repeated_then_cache_stays_disabled(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: PolicyResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="verified hermetic custom rule keeps cache",
            body="del model\n    return []",
            require_cacheable=True,
            expected_cache_hits=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hermetic_custom_rule_when_cache_required_then_second_run_hits_cache(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: PolicyResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="nonhermetic cacheable rule fails",
            body='open("policy.txt")\n    return []',
            require_cacheable=True,
            expected_error_pattern=r"custom.py:\d+: call to open",
        ),
        CustomRuleTestCase(
            description="model-local cacheable rule cannot read project-wide facts",
            body="del model\n    _ = ctx.public_enums\n    return []",
            require_cacheable=True,
            expected_error_pattern=r"uses project-wide context public_enums",
        ),
        CustomRuleTestCase(
            description="project-wide cacheable rule rejects untracked file types",
            body=(
                'del model\n    _ = ctx.project_read_text(path="policy/input.json")\n    return []'
            ),
            require_cacheable=True,
            project_wide=True,
            expected_error_pattern=r"project policy input must be a tracked file type",
        ),
        CustomRuleTestCase(
            description="project-wide rule rejects untracked file types",
            body=(
                'del model\n    _ = ctx.project_read_text(path="policy/input.json")\n    return []'
            ),
            require_cacheable=True,
            project_wide=True,
            expected_error_pattern=r"project policy input must be a tracked file type",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_nonhermetic_custom_rule_when_cache_required_then_raises_file_line_error(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    with pytest.raises(PolicyError, match=test_case.expected_error_pattern):
        evaluate(project=project, config=config, project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="project-wide rule reads project facts",
            body="del model\n    _ = ctx.public_enums\n    return []",
            require_cacheable=True,
            project_wide=True,
            expected_cache_hits=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_wide_rule_when_reading_project_context_then_cache_is_allowed(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    _ = evaluate(project=project, config=config, project_dir=tmp_path)
    result: PolicyResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert result.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    (
        CustomRuleSuppressionTestCase(
            description="exact exception suppresses custom finding",
            rule_exceptions=(
                RuleExemption(
                    rule="XSQBPT101",
                    path="models/mart/market__mart__prices.sql",
                    reason="Tracked custom-rule migration",
                ),
            ),
            rule_ignores=(),
            expected_fault_codes=(),
        ),
        CustomRuleSuppressionTestCase(
            description="scoped ignore suppresses custom finding",
            rule_exceptions=(),
            rule_ignores=(
                RuleIgnore(
                    rules=("XSQBPT",),
                    paths=("models/mart/**",),
                    reason="Tracked custom-rule migration",
                ),
            ),
            expected_fault_codes=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_common_suppression_when_custom_rule_faults_then_native_policy_suppresses_it(
    tmp_path: Path,
    test_case: CustomRuleSuppressionTestCase,
) -> None:
    custom_rule_case: CustomRuleTestCase = CustomRuleTestCase(
        description=test_case.description,
        body="del model\n    return [ctx.path_fault()]",
        require_cacheable=False,
    )
    project: CompiledProject
    config: PolicyConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=custom_rule_case)
    relative_path: str = "models/mart/market__mart__prices.sql"
    target: Path = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text("WITH final AS (SELECT 1 AS id) SELECT id FROM final\n", encoding="utf-8")
    config = replace(
        config,
        rule_exceptions=test_case.rule_exceptions,
        rule_ignores=test_case.rule_ignores,
    )

    result: PolicyResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert tuple(fault.code for fault in result.faults) == test_case.expected_fault_codes
