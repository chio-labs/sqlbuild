"""Real-pipeline custom rule harness."""

from __future__ import annotations

import inspect
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlbuild._native import (
    MIN_CUSTOM_RULE_TEST_CASES,
    DiscoveredProjectInputs,
    Rule,
    RuleAssertionError,
    RuleCase,
    RuleResult,
    RulesConfig,
    RulesResult,
    RuleUsageError,
    build_compiled_project,
    discover_project_inputs,
    evaluate_project_rules,
    load_rules_config,
    rule_option_toml_value,
)
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.rule_engine._helpers.engine.definition import (
    resolve_rule_signature,
    rule_from_value,
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
        project: CompiledProjectView = _compile_rule_project(root=root)
        config: RulesConfig = load_rules_config(project_dir=root)
        result: RulesResult = evaluate_project_rules(
            project=project,
            config=config,
            project_dir=root,
            verify_determinism=True,
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
            config_lines.append(f"{name} = {rule_option_toml_value(value)}")
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


def _compile_rule_project(*, root: Path) -> CompiledProjectView:
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=root)
    adapter: DuckDbAdapter = DuckDbAdapter()
    return build_compiled_project(discovered_inputs=discovered, adapter=adapter)
