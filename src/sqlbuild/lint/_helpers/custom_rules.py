"""Capability-bounded custom SQL lint authoring and execution."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.lint._helpers.native_sql import _authored_violation
from sqlbuild.lint.classes.rule_context import LintRuleContext
from sqlbuild.lint.exceptions import CustomLintError
from sqlbuild.lint.models import (
    CustomLintFinding,
    CustomLintRule,
    LintBody,
    LintConfig,
    LintRuleOption,
    LintViolation,
)
from sqlbuild.lint.types import CustomLintCheck

_RULE_ATTRIBUTE: str = "__sqlbuild_custom_lint_rule__"
_RULE_CODE: re.Pattern[str] = re.compile(r"^XSQBL[A-Z][0-9]{3}$")
_DECORATOR_TOKEN: str = "@lint_rule"
_CONTEXT_PARAMETER: str = "ctx"


def define_lint_rule(
    *,
    code: str,
    family: str,
    slug: str,
    message: str,
    remediation: str,
    options: tuple[LintRuleOption[object], ...] = (),
) -> Callable[[CustomLintCheck], CustomLintCheck]:
    """Declare one repository-owned statement-local lint rule."""

    def decorate(check: CustomLintCheck) -> CustomLintCheck:
        if not _RULE_CODE.fullmatch(code):
            raise CustomLintError(
                f"custom SQL lint rule code must match XSQBL<family><number>: {code}"
            )
        if not all(value.strip() for value in (family, slug, message, remediation)):
            raise CustomLintError(f"custom lint rule {code} has incomplete metadata")
        parameters: tuple[inspect.Parameter, ...] = tuple(
            inspect.signature(check).parameters.values()
        )
        if (
            len(parameters) != 1
            or parameters[0].name != _CONTEXT_PARAMETER
            or (parameters[0].kind is not inspect.Parameter.KEYWORD_ONLY)
        ):
            raise CustomLintError(
                f"custom lint rule {code} must use def check(*, ctx: LintRuleContext)"
            )
        names: tuple[str, ...] = tuple(option.name for option in options)
        if len(names) != len(set(names)):
            raise CustomLintError(f"custom lint rule {code} declares duplicate option names")
        rule: CustomLintRule = CustomLintRule(
            code=code,
            family=family,
            slug=slug,
            message=message,
            remediation=remediation,
            check=check,
            options=options,
        )
        setattr(check, _RULE_ATTRIBUTE, rule)
        return check

    return decorate


def run_custom_lint_rules(
    *,
    bodies: tuple[LintBody, ...],
    contents_by_path: dict[Path, str],
    config: LintConfig,
    project_dir: Path,
) -> tuple[LintViolation, ...]:
    """Evaluate selected custom rules over prepared statement bodies."""

    rules: tuple[CustomLintRule, ...] = _select_rules(
        rules=_load_rules(config=config, project_dir=project_dir), config=config
    )
    if not rules:
        return ()
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise CustomLintError("custom SQL lint requires the bundled polyglot_sql package")
    violations: list[LintViolation] = []
    for body in bodies:
        try:
            ast: Any = polyglot.parse_one(body.lint_text, dialect=config.dialect)
        except Exception as error:
            raise CustomLintError(f"could not parse SQL for custom lint: {error}") from error
        for rule in rules:
            context: LintRuleContext = LintRuleContext(
                source=body.lint_text,
                dialect=config.dialect,
                ast=ast,
                rule=rule,
                options=config.custom_rule_options.get(rule.code, {}),
            )
            try:
                findings: Iterable[CustomLintFinding] = rule.check(ctx=context)
                for finding in findings:
                    violation: LintViolation | None = _finding_violation(
                        finding=finding,
                        rule=rule,
                        body=body,
                        contents=contents_by_path[body.file_path],
                    )
                    if violation is not None:
                        violations.append(violation)
            except CustomLintError:
                raise
            except Exception as error:
                raise CustomLintError(f"custom lint rule {rule.code} failed: {error}") from error
    return tuple(violations)


def run_lint_rule(
    *,
    rule: CustomLintCheck | CustomLintRule,
    source: str,
    dialect: str = "generic",
) -> tuple[CustomLintFinding, ...]:
    """Evaluate one custom rule without project discovery."""

    resolved: CustomLintRule | None = (
        rule if isinstance(rule, CustomLintRule) else _rule_from_value(rule)
    )
    if resolved is None:
        raise CustomLintError("evaluate_lint_rule requires a @lint_rule-decorated check")
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise CustomLintError("custom SQL lint requires the bundled polyglot_sql package")
    ast: Any = polyglot.parse_one(source, dialect=dialect)
    context: LintRuleContext = LintRuleContext(
        source=source,
        dialect=dialect,
        ast=ast,
        rule=resolved,
        options={},
    )
    return tuple(resolved.check(ctx=context))


def _finding_violation(
    *,
    finding: CustomLintFinding,
    rule: CustomLintRule,
    body: LintBody,
    contents: str,
) -> LintViolation | None:
    if finding.code != rule.code:
        raise CustomLintError(f"custom lint rule {rule.code} returned finding for {finding.code}")
    violation: LintViolation | None = _authored_violation(
        raw_diagnostic={
            "code": finding.code,
            "message": finding.message,
            "remediation": finding.remediation,
            "start": finding.start,
            "end": finding.end,
            "fix": None,
            "fix_unavailable_reason": "custom lint rules are diagnostics-only",
        },
        body=body,
        contents=contents,
    )
    if violation is None:
        return None
    return LintViolation(
        file_path=violation.file_path,
        line=violation.line,
        column=violation.column,
        code=violation.code,
        message=violation.message,
        severity=violation.severity,
        engine="custom",
        end_line=violation.end_line,
        end_column=violation.end_column,
        remediation=violation.remediation,
        fix_unavailable_reason=violation.fix_unavailable_reason,
    )


def _load_rules(*, config: LintConfig, project_dir: Path) -> tuple[CustomLintRule, ...]:
    modules: list[ModuleType] = []
    repository_path: str = str(project_dir.resolve())
    sys.path.insert(0, repository_path)
    try:
        for name in config.custom_rule_modules:
            try:
                module: ModuleType = importlib.import_module(name)
            except Exception as error:
                raise CustomLintError(
                    f"could not import custom lint rule module {name}: {error}"
                ) from error
            source: str | None = inspect.getsourcefile(module)
            if source is None or not Path(source).resolve().is_relative_to(project_dir.resolve()):
                raise CustomLintError(f"custom lint rule module {name} must be repository-owned")
            modules.append(module)
    finally:
        sys.path.remove(repository_path)
    for configured in config.custom_rule_paths:
        path: Path = (project_dir / configured).resolve()
        if not path.is_relative_to(project_dir.resolve()):
            raise CustomLintError(f"custom lint rule path escapes project: {configured}")
        candidates: tuple[Path, ...] = (
            tuple(sorted(path.rglob("*.py"))) if path.is_dir() else (path,)
        )
        for candidate in candidates:
            if not candidate.is_file():
                raise CustomLintError(f"custom lint rule path does not exist: {candidate}")
            if path.is_dir() and _DECORATOR_TOKEN not in candidate.read_text(encoding="utf-8"):
                continue
            modules.append(_load_file(candidate))
    collected: list[CustomLintRule] = []
    for module in modules:
        collected.extend(_module_rules(module))
    rules: tuple[CustomLintRule, ...] = tuple(collected)
    codes: tuple[str, ...] = tuple(rule.code for rule in rules)
    duplicates: list[str] = sorted(code for code in set(codes) if codes.count(code) > 1)
    if duplicates:
        raise CustomLintError(f"duplicate custom lint rule codes: {', '.join(duplicates)}")
    _validate_options(rules=rules, configured=config.custom_rule_options)
    return tuple(sorted(rules, key=lambda item: item.code))


def _validate_options(
    *,
    rules: tuple[CustomLintRule, ...],
    configured: Mapping[str, Mapping[str, object]],
) -> None:
    by_code: dict[str, CustomLintRule] = {rule.code: rule for rule in rules}
    unknown_codes: list[str] = sorted(set(configured) - set(by_code))
    if unknown_codes:
        raise CustomLintError(
            f"custom lint options target unknown rules: {', '.join(unknown_codes)}"
        )
    for code, values in configured.items():
        options: dict[str, LintRuleOption[object]] = {
            option.name: option for option in by_code[code].options
        }
        unknown_names: list[str] = sorted(set(values) - set(options))
        if unknown_names:
            raise CustomLintError(
                f"custom lint rule {code} has unknown options: {', '.join(unknown_names)}"
            )
        for name, value in values.items():
            expected: type[object] = options[name].value_type
            if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
                raise CustomLintError(
                    f"custom lint option {code}.{name} must be {expected.__name__}"
                )


def _select_rules(
    *, rules: tuple[CustomLintRule, ...], config: LintConfig
) -> tuple[CustomLintRule, ...]:
    if not config.selected_custom_rules:
        return ()
    for selector in config.selected_custom_rules:
        if not any(rule.code.startswith(selector) for rule in rules):
            raise CustomLintError(f"custom lint selector matches no rules: {selector}")
    for selector in config.ignored_custom_rules:
        if not any(rule.code.startswith(selector) for rule in rules):
            raise CustomLintError(f"custom lint ignore matches no rules: {selector}")
    selected: list[CustomLintRule] = []
    for rule in rules:
        enabled: bool = any(
            rule.code.startswith(selector) for selector in config.selected_custom_rules
        )
        ignored: bool = any(
            rule.code.startswith(selector) for selector in config.ignored_custom_rules
        )
        if enabled and not ignored:
            selected.append(rule)
    return tuple(selected)


def _load_file(path: Path) -> ModuleType:
    digest: str = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    name = f"sqlbuild._loaded_lint_{digest}"
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CustomLintError(f"could not load custom lint rule file {path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise CustomLintError(f"could not import custom lint rule file {path}: {error}") from error
    return module


def _module_rules(module: ModuleType) -> tuple[CustomLintRule, ...]:
    return tuple(
        rule
        for value in vars(module).values()
        if getattr(value, "__module__", None) == module.__name__
        and (rule := _rule_from_value(value)) is not None
    )


def _rule_from_value(value: object) -> CustomLintRule | None:
    rule: object = getattr(value, _RULE_ATTRIBUTE, None)
    return cast(CustomLintRule, rule) if isinstance(rule, CustomLintRule) else None
