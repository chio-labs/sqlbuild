"""Real-pipeline custom rule harness."""

from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.rule_engine._helpers.engine.config import load_rules_config
from sqlbuild.rule_engine._helpers.engine.definition import (
    resolve_rule_signature,
    rule_from_value,
)
from sqlbuild.rule_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.rule_engine.exceptions import RuleAssertionError, RuleUsageError
from sqlbuild.rule_engine.main._evaluate import evaluate
from sqlbuild.rule_engine.models import (
    Rule,
    RuleCase,
    RuleResult,
    RulesConfig,
    RulesResult,
)
from sqlbuild.rule_engine.types import RuleCheck


def run_rule_case(*, rule: RuleCheck | Rule, test_case: RuleCase) -> RuleResult:
    """Evaluate one rule through project discovery, compilation, and rule evaluation."""

    resolved: Rule | None = rule if isinstance(rule, Rule) else rule_from_value(value=rule)
    if resolved is None:
        raise RuleUsageError("evaluate_rule requires a @rule function")
    resolved = resolve_rule_signature(rule=resolved)
    with TemporaryDirectory(prefix="sqlbuild-rule-") as temporary:
        root: Path = Path(temporary)
        _ = _write_rule_project(root=root, rule=resolved, test_case=test_case)
        project: CompiledProject = _compile_rule_project(root=root)
        config: RulesConfig = load_rules_config(root)
        result: RulesResult = evaluate(
            project=project,
            config=config,
            project_dir=root,
        )
    if len(result.findings) != test_case.expected_finding_count:
        raise RuleAssertionError(
            f"{test_case.description}: expected {test_case.expected_finding_count} findings, "
            f"found {len(result.findings)}"
        )
    return RuleResult(findings=result.findings)


def _write_rule_project(*, root: Path, rule: Rule, test_case: RuleCase) -> Path:
    config_lines: list[str] = [
        'name = "rule_test"',
        'adapter = "duckdb"',
        'default_target = "dev"',
        "",
        "[targets.dev]",
        'schema = "main"',
        "",
        "[rules]",
        f'select = ["{rule.code}"]',
        "",
        "[rules.thresholds]",
        f"{MIN_CUSTOM_RULE_TEST_CASES} = 0",
        "",
    ]
    if test_case.config:
        config_lines.append(f"[rules.rule_options.{rule.code}]")
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
        raise RuleUsageError("evaluate_rule requires a rule declared in a source file")
    rule_path: Path = root / "rules" / "custom.py"
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
    raise RuleUsageError(f"RuleCase config value {value!r} cannot be represented as a rule option")


def _compile_rule_project(*, root: Path) -> CompiledProject:
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=root)
    adapter: DuckDbAdapter = DuckDbAdapter()
    return compile_project(discovered_inputs=discovered, adapter=adapter)
