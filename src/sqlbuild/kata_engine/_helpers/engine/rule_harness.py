"""Real-pipeline custom kata rule harness."""

from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.kata_engine._helpers.engine.config import load_kata_config
from sqlbuild.kata_engine._helpers.engine.definition import rule_from_value
from sqlbuild.kata_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.kata_engine.exceptions import KataRuleAssertionError, KataRuleUsageError
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataConfig, KataResult, KataRule, RuleCase, RuleResult
from sqlbuild.kata_engine.types import KataCheck


def run_rule_case(*, rule: KataCheck | KataRule, test_case: RuleCase) -> RuleResult:
    """Evaluate one rule through project discovery, compilation, and kata evaluation."""

    resolved: KataRule | None = rule if isinstance(rule, KataRule) else rule_from_value(value=rule)
    if resolved is None:
        raise KataRuleUsageError("evaluate_rule requires a @kata rule or KataRule")
    with TemporaryDirectory(prefix="sqlbuild-kata-rule-") as temporary:
        root: Path = Path(temporary)
        _ = _write_rule_project(root=root, rule=resolved, test_case=test_case)
        project: CompiledProject = _compile_rule_project(root=root)
        config: KataConfig = load_kata_config(root)
        result: KataResult = evaluate(
            project=project,
            config=config,
            project_dir=root,
        )
    if len(result.faults) != test_case.expected_fault_count:
        raise KataRuleAssertionError(
            f"{test_case.description}: expected {test_case.expected_fault_count} faults, "
            f"found {len(result.faults)}"
        )
    return RuleResult(faults=result.faults)


def _write_rule_project(*, root: Path, rule: KataRule, test_case: RuleCase) -> Path:
    config_lines: list[str] = [
        'name = "kata_rule_test"',
        'adapter = "duckdb"',
        'default_target = "dev"',
        "",
        "[targets.dev]",
        'schema = "main"',
        "",
        "[kata]",
        f'select = ["{rule.code}"]',
        'rule_paths = ["kata/rules/custom.py"]',
        "",
        "[kata.thresholds]",
        f"{MIN_CUSTOM_RULE_TEST_CASES} = 0",
        "",
    ]
    if test_case.config:
        config_lines.append(f"[kata.rule_options.{rule.code}]")
        for name, value in sorted(test_case.config.items()):
            config_lines.append(f"{name} = {_toml_value(value=value)}")
        config_lines.append("")
    project_config: str = "\n".join(config_lines)
    (root / "sqlbuild_project.toml").write_text(project_config, encoding="utf-8")
    model_path: Path = root / test_case.path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(test_case.source, encoding="utf-8")
    for file in test_case.files:
        extra_path: Path = root / file.path
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text(file.source, encoding="utf-8")
    source: str | None = inspect.getsourcefile(rule.check)
    if source is None or not Path(source).is_file():
        raise KataRuleUsageError("evaluate_rule requires a rule declared in a source file")
    rule_path: Path = root / "kata" / "rules" / "custom.py"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")
    return rule_path


def _toml_value(*, value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped: str = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(value=item) for item in value) + "]"
    raise KataRuleUsageError(
        f"RuleCase config value {value!r} cannot be represented as a kata rule option"
    )


def _compile_rule_project(*, root: Path) -> CompiledProject:
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=root)
    adapter: DuckDbAdapter = DuckDbAdapter()
    return compile_project(discovered_inputs=discovered, adapter=adapter)
