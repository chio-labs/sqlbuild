"""Custom-rule loading and hermeticity behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataConfig, KataResult
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import CustomRuleTestCase
from tests.unit.src.sqlbuild.kata_engine._helpers.engine.helpers import custom_rule_inputs


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="selected custom rule faults",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            expected_fault_codes=("XSQBKT001",),
        ),
        CustomRuleTestCase(
            description="untested custom rule faults coverage",
            body="del model\n    return []",
            require_cacheable=False,
            expected_fault_codes=("SQBKX201",),
            minimum_custom_rule_cases=1,
        ),
        CustomRuleTestCase(
            description="default-off custom rule is not activated by prefix",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            select=("XSQBKT",),
        ),
        CustomRuleTestCase(
            description="default-enabled custom rule is activated by prefix",
            body="del model\n    return [ctx.path_fault()]",
            require_cacheable=False,
            expected_fault_codes=("XSQBKT001",),
            select=("XSQBKT",),
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
    config: KataConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    result: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert tuple(fault.code for fault in result.faults) == test_case.expected_fault_codes


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
    config: KataConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

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
    config: KataConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)
    _ = evaluate(project=project, config=config, project_dir=tmp_path)

    second: KataResult = evaluate(project=project, config=config, project_dir=tmp_path)

    assert second.cache_hits == test_case.expected_cache_hits


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="nonhermetic cacheable rule fails",
            body='open("policy.txt")\n    return []',
            require_cacheable=True,
            expected_error_pattern=r"custom.py:\d+: call to open",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nonhermetic_custom_rule_when_cache_required_then_raises_file_line_error(
    tmp_path: Path,
    test_case: CustomRuleTestCase,
) -> None:
    project: CompiledProject
    config: KataConfig
    project, config = custom_rule_inputs(tmp_path=tmp_path, test_case=test_case)

    with pytest.raises(KataError, match=test_case.expected_error_pattern):
        evaluate(project=project, config=config, project_dir=tmp_path)
