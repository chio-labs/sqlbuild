"""Real CLI coverage of per-Rule custom-rule timings, `--no-cache` and module-state attribution."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    CustomRuleTimingCase,
    ModuleStateAttributionCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import (
    custom_rule_cache_counts,
    custom_rule_source,
    custom_rule_timings,
    rule_cache_hits,
    run_compile_cli,
    split_model_files,
    write_custom_rule_project,
)

_FULL_COMPILE: tuple[tuple[str, str], ...] = (
    ("SQLBUILD_DISABLE_COMPILE_REUSE", "1"),
    ("SQLBUILD_DISABLE_DELTA_COMPILE", "1"),
)
_MODEL_COUNT: int = 4
_RULE_HEADER: str = "from sqlbuild.rules import Finding, Model, RuleContext, rule\n"


def _rule(*, code: str, body: str, header: str = _RULE_HEADER, function: str = "check") -> str:
    return custom_rule_source(code=code, header=header, body=body).replace(
        "def check(", f"def {function}(", 1
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTimingCase(
            description="two model rules in separate files",
            model_count=_MODEL_COUNT,
            selected_rules=("XSQBRTIME001", "XSQBRTIME002"),
            files=(
                (
                    "rules/names.py",
                    _rule(code="XSQBRTIME001", body="    return [] if model.name else []\n"),
                ),
                (
                    "rules/paths.py",
                    _rule(
                        code="XSQBRTIME002",
                        body="    return [] if model.path.suffix == '.sql' else []\n",
                    ),
                ),
                *split_model_files(_MODEL_COUNT),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_rules_when_compiling_then_timings_and_no_cache_report_each_rule(
    tmp_path: Path, test_case: CustomRuleTimingCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path, selected_rules=test_case.selected_rules, files=test_case.files
    )
    subjects: int = test_case.model_count + 1

    cold: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path, environment=_FULL_COMPILE)
    warm: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path, environment=_FULL_COMPILE)
    uncached: subprocess.CompletedProcess[str] = run_compile_cli(
        tmp_path, environment=_FULL_COMPILE, arguments=("--no-cache",)
    )
    rewarmed: subprocess.CompletedProcess[str] = run_compile_cli(
        tmp_path, environment=_FULL_COMPILE
    )

    for result in (cold, warm, uncached, rewarmed):
        assert result.returncode == 0, result.stdout + result.stderr
    evaluated: dict[str, tuple[int, int, int]] = {
        code: (subjects, 0, subjects) for code in test_case.selected_rules
    }
    reused: dict[str, tuple[int, int, int]] = {
        code: (0, subjects, 0) for code in test_case.selected_rules
    }
    assert custom_rule_cache_counts(cold) == evaluated
    assert custom_rule_cache_counts(warm) == reused
    assert custom_rule_cache_counts(uncached) == evaluated
    assert rule_cache_hits(uncached) == 0
    assert custom_rule_cache_counts(rewarmed) == reused
    cold_timings: dict[str, int] = json.loads(cold.stdout)["compile_timings"]
    assert cold_timings["custom_rules_invocations"] == subjects * len(test_case.selected_rules)
    assert cold_timings["custom_rules_monitor_cpu_ms"] >= 0
    assert cold_timings["custom_rules_guard_cpu_ms"] >= 0
    assert all(cpu_ms >= 0 for _, cpu_ms, _, _ in custom_rule_timings(cold).values())
    assert json.loads(warm.stdout)["compile_timings"]["custom_rules_invocations"] == 0


@pytest.mark.parametrize(
    "test_case",
    [
        ModuleStateAttributionCase(
            description="a persistent mutation is attributed, one undone within a model is not",
            model_count=_MODEL_COUNT,
            selected_rules=("XSQBRSTATE001", "XSQBRSTATE002", "XSQBRSTATE003", "XSQBRSTATE004"),
            files=(
                (
                    "rules/persistent.py",
                    _rule(
                        code="XSQBRSTATE001",
                        header=_RULE_HEADER + "SEEN: list[str] = []\n",
                        body="    SEEN.append(model.name)\n    return []\n",
                    ),
                ),
                (
                    "rules/transient.py",
                    _rule(
                        code="XSQBRSTATE002",
                        header=_RULE_HEADER + "SCRATCH: list[str] = []\n",
                        body="    SCRATCH.append(model.name)\n    return []\n",
                        function="stage",
                    )
                    + "\n\n"
                    + _rule(
                        code="XSQBRSTATE003",
                        header="",
                        body="    SCRATCH.clear()\n    return []\n",
                        function="restore",
                    ),
                ),
                (
                    "rules/clean.py",
                    _rule(code="XSQBRSTATE004", body="    return [] if model.name else []\n"),
                ),
                *split_model_files(_MODEL_COUNT),
            ),
            edited_model="models/orders_001.sql",
            expected_misses_after_edit={
                "XSQBRSTATE001": _MODEL_COUNT + 1,
                "XSQBRSTATE002": 0,
                "XSQBRSTATE003": 0,
                "XSQBRSTATE004": 0,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rule_module_state_when_recompiling_an_edit_then_only_persistent_state_is_untracked(
    tmp_path: Path, test_case: ModuleStateAttributionCase
) -> None:
    write_custom_rule_project(
        project_dir=tmp_path, selected_rules=test_case.selected_rules, files=test_case.files
    )

    cold: subprocess.CompletedProcess[str] = run_compile_cli(tmp_path, environment=_FULL_COMPILE)
    (tmp_path / test_case.edited_model).write_text(
        'MODEL (description "Orders");\nSELECT 2 AS order_id\n', encoding="utf-8"
    )
    edited: subprocess.CompletedProcess[str] = run_compile_cli(
        tmp_path, environment=_FULL_COMPILE
    )

    assert cold.returncode == 0, cold.stdout + cold.stderr
    assert edited.returncode == 0, edited.stdout + edited.stderr
    assert {
        code: misses for code, (_, _, misses) in custom_rule_cache_counts(edited).items()
    } == test_case.expected_misses_after_edit
