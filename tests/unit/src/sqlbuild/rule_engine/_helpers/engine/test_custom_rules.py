"""Custom-rule loading and hermeticity behavior tests."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.main._evaluate import evaluate
from sqlbuild.rule_engine.models import (
    RuleExemption,
    RuleIgnore,
    RulesConfig,
    RulesResult,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    CustomRuleCacheDependencyTestCase,
    CustomRuleSuppressionTestCase,
    CustomRuleTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import custom_rule_inputs


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="selected custom rule faults",
            body="return [ctx.finding(subject=model)]",
            expected_fault_codes=("XSQBRT101",),
            expected_fault_lines=(1,),
        ),
        CustomRuleTestCase(
            description="untested custom rule faults coverage",
            body="del model\n    return []",
            expected_fault_codes=("SQBRTEST301",),
            expected_fault_lines=(4,),
            minimum_custom_rule_cases=1,
        ),
        CustomRuleTestCase(
            description="default-off custom rule is not activated by prefix",
            body="return [ctx.finding(subject=model)]",
            select=("XSQBRT",),
        ),
        CustomRuleTestCase(
            description="default-enabled custom rule is activated by prefix",
            body="return [ctx.finding(subject=model)]",
            expected_fault_codes=("XSQBRT101",),
            expected_fault_lines=(1,),
            select=("XSQBRT",),
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
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    result: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert tuple(fault.code for fault in result.findings) == test_case.expected_fault_codes
    assert tuple(fault.line for fault in result.findings) == test_case.expected_fault_lines


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="custom rule uses deterministic cache",
            body="del model\n    return []",
            expected_cache_hits=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_rule_when_repeated_then_deterministic_cache_is_reused(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="verified hermetic custom rule keeps cache",
            body="del model\n    return []",
            expected_cache_hits=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_hermetic_custom_rule_when_cache_required_then_second_run_hits_cache(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleCacheDependencyTestCase(
            description="model-only rule ignores unrelated project file changes",
            body="del model\n    return []",
            changed_path="config/new.yml",
            expected_cache_hits=1,
        ),
        CustomRuleCacheDependencyTestCase(
            description="graph-observing rule ignores unrelated project file changes",
            body="_ = ctx.graph.dependencies(model)\n    return []",
            changed_path="config/new.yml",
            expected_cache_hits=1,
        ),
        CustomRuleCacheDependencyTestCase(
            description="negative project glob observes a newly matching file",
            body=('del model\n    _ = ctx.project.tree.glob("config/**/*.yml")\n    return []'),
            changed_path="config/new.yml",
            expected_cache_hits=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_file_change_when_repeating_custom_rule_then_dependencies_control_cache(
    tmp_path: Path,
    test_case: CustomRuleCacheDependencyTestCase,
) -> None:
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(
        tmp_path=tmp_path,
        test_case=CustomRuleTestCase(description=test_case.description, body=test_case.body),
    )
    _ = evaluate(project=project, config=config, project_dir=tmp_path)
    changed_path: Path = tmp_path / test_case.changed_path
    changed_path.parent.mkdir(parents=True)
    changed_path.write_text("enabled: true\n", encoding="utf-8")

    second: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="nonhermetic cacheable rule fails",
            body='open("policy.txt")\n    return []',
            expected_error_pattern=r"custom.py:\d+: call to open",
        ),
        CustomRuleTestCase(
            description="project-wide cacheable rule rejects untracked file types",
            body=(
                'del model\n    _ = ctx.project.tree.read_text("rules/input.json")\n    return []'
            ),
            project_wide=True,
            expected_error_pattern=r"compiler rules input must be a tracked file type",
        ),
        CustomRuleTestCase(
            description="project-wide rule rejects untracked file types",
            body=(
                'del model\n    _ = ctx.project.tree.read_text("rules/input.json")\n    return []'
            ),
            project_wide=True,
            expected_error_pattern=r"compiler rules input must be a tracked file type",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_nonhermetic_custom_rule_when_cache_required_then_raises_file_line_error(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    with pytest.raises(RulesError, match=test_case.expected_error_pattern):
        evaluate(project=project, config=config, project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="project-wide rule reads project facts",
            body="del model\n    _ = ctx.declarations.public_enums\n    return []",
            project_wide=True,
            expected_cache_hits=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_wide_rule_when_reading_project_context_then_cache_is_allowed(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    _ = evaluate(project=project, config=config, project_dir=tmp_path)
    result: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert result.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    (
        CustomRuleSuppressionTestCase(
            description="exact exception suppresses custom finding",
            rule_exceptions=(
                RuleExemption(
                    rule="XSQBRT101",
                    path="models/mart/commerce__mart__orders.sql",
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
                    rules=("XSQBRT",),
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
        body="return [ctx.finding(subject=model)]",
    )
    project: CompiledProject
    config: RulesConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=custom_rule_case)
    relative_path: str = "models/mart/commerce__mart__orders.sql"
    target: Path = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text("WITH final AS (SELECT 1 AS id) SELECT id FROM final\n", encoding="utf-8")
    config = replace(
        config,
        rule_exceptions=test_case.rule_exceptions,
        rule_ignores=test_case.rule_ignores,
    )

    result: RulesResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert tuple(fault.code for fault in result.findings) == test_case.expected_fault_codes
