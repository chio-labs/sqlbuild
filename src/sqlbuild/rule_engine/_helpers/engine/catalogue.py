"""Built-in and custom rule catalogue construction."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import replace
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild.rule_engine._helpers.engine.definition import (
    resolve_rule_signature,
    rule_from_value,
)
from sqlbuild.rule_engine._helpers.engine.native import native_catalogue, native_selected_codes
from sqlbuild.rule_engine.constants import INIT_MODULE_NAME, RULE_DECORATOR_TOKEN
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    Finding,
    Rule,
    RuleGuidance,
    RuleOption,
    RulesConfig,
)
from sqlbuild.rule_engine.types import RuleSubject


def build_catalogue(
    *, config: RulesConfig, project_dir: Path, include_custom: bool = True
) -> tuple[Rule, ...]:
    """Build and validate the complete configured rule catalogue."""

    rules_dir: Path = project_dir / "rules"
    custom: tuple[Rule, ...] = (
        (_load_paths(paths=("rules",), project_dir=project_dir) if rules_dir.is_dir() else ())
        if include_custom
        else ()
    )
    rules: tuple[Rule, ...] = (*_builtins(), *custom)
    codes: tuple[str, ...] = tuple(rule.code for rule in rules)
    duplicates: tuple[str, ...] = tuple(
        sorted(code for code in set(codes) if codes.count(code) > 1)
    )
    if duplicates:
        raise RulesError(f"duplicate rule codes: {', '.join(duplicates)}")
    for rule in rules:
        _validate_options(rule=rule, configured=config.rule_options.get(rule.code, {}))
    configured_codes: set[str] = set(config.rule_options)
    unknown_option_codes: set[str] = configured_codes - set(codes)
    if unknown_option_codes:
        raise RulesError(
            f"rule options target unknown codes: {', '.join(sorted(unknown_option_codes))}"
        )
    return tuple(sorted(rules, key=lambda item: item.code))


def _builtins() -> tuple[Rule, ...]:
    return tuple(
        Rule(
            code=str(item["code"]),
            family=str(item["code"])[:-3],
            slug=str(item["slug"]),
            message=str(item["message"]),
            remediation=str(item["remediation"]),
            check=_native_builtin,
            enabled_by_default=bool(item["enabled_by_default"]),
            subject=(RuleSubject.PROJECT if bool(item["project_wide"]) else RuleSubject.MODEL),
            guidance=_guidance(item.get("guidance")),
        )
        for item in native_catalogue()
    )


def _guidance(value: object) -> RuleGuidance | None:
    if not isinstance(value, dict):
        return None
    payload: dict[str, object] = {str(key): item for key, item in value.items()}
    return RuleGuidance(
        good_example=str(payload["good_example"]),
        anti_tautology=str(payload["anti_tautology"]),
        mutation_check=str(payload["mutation_check"]),
    )


def _native_builtin(*, model: object, ctx: object) -> list[Finding]:
    del model, ctx
    raise RulesError("built-in rules execute only through the native engine")


def select_rules(
    *, catalogue: tuple[Rule, ...], config: RulesConfig, project_dir: Path
) -> tuple[Rule, ...]:
    """Resolve the active catalogue through the native Fensu rules owner."""

    by_code: dict[str, Rule] = {rule.code: rule for rule in catalogue}
    codes: tuple[str, ...] = native_selected_codes(
        config=config, catalogue=catalogue, project_dir=project_dir
    )
    try:
        return tuple(by_code[code] for code in codes)
    except KeyError as error:
        raise RulesError(f"native compiler rules returned unknown rule {error.args[0]}") from error


def _load_paths(*, paths: tuple[str, ...], project_dir: Path) -> tuple[Rule, ...]:
    result: list[Rule] = []
    existing_modules: frozenset[str] = frozenset(sys.modules)
    repository_path: str = str(project_dir.resolve())
    sys.path.insert(0, repository_path)
    try:
        for configured in paths:
            path: Path = (project_dir / configured).resolve()
            if not path.is_relative_to(project_dir.resolve()):
                raise RulesError(f"rule path escapes the project: {configured}")
            configured_directory: bool = path.is_dir()
            files: tuple[Path, ...] = (
                tuple(sorted(path.rglob("*.py"))) if path.is_dir() else (path,)
            )
            for file_path in files:
                if not file_path.is_file():
                    raise RulesError(f"rule path does not exist: {file_path}")
                if configured_directory and RULE_DECORATOR_TOKEN not in file_path.read_text(
                    encoding="utf-8"
                ):
                    continue
                name: str = _rule_module_name(file_path=file_path, project_dir=project_dir)
                spec: ModuleSpec | None = importlib.util.spec_from_file_location(name, file_path)
                if spec is None or spec.loader is None:
                    raise RulesError(f"could not load rule file {file_path}")
                module: ModuleType = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as error:
                    raise RulesError(f"could not import rule file {file_path}: {error}") from error
                finally:
                    _ = sys.modules.pop(name, None)
                result.extend(
                    _module_rules(
                        module=module,
                        source=file_path,
                        require_rules=not configured_directory,
                    )
                )
    finally:
        sys.path.remove(repository_path)
        _remove_loaded_project_modules(
            existing_modules=existing_modules,
            project_dir=project_dir,
        )
    return tuple(result)


def _rule_module_name(*, file_path: Path, project_dir: Path) -> str:
    relative: Path = file_path.relative_to(project_dir.resolve()).with_suffix("")
    parts: tuple[str, ...] = relative.parts
    if parts[-1] == INIT_MODULE_NAME:
        parts = parts[:-1]
    return ".".join(parts)


def _module_rules(
    *, module: ModuleType, source: Path, require_rules: bool = True
) -> tuple[Rule, ...]:
    rules: tuple[Rule, ...] = tuple(
        resolve_rule_signature(rule=rule)
        for value in vars(module).values()
        if getattr(value, "__module__", None) == module.__name__
        and (rule := rule_from_value(value=value)) is not None
    )
    if not rules and require_rules:
        raise RulesError(f"rule source exposes no @rule functions: {source}")
    return tuple(replace(rule, source=source.as_posix()) for rule in rules)


def _remove_loaded_project_modules(*, existing_modules: frozenset[str], project_dir: Path) -> None:
    for name in tuple(sys.modules):
        if name in existing_modules:
            continue
        module: object = sys.modules.get(name)
        source: object = getattr(module, "__file__", None)
        if isinstance(source, str) and Path(source).resolve().is_relative_to(project_dir.resolve()):
            _ = sys.modules.pop(name, None)


def _validate_options(*, rule: Rule, configured: Mapping[str, object]) -> None:
    declarations: dict[str, RuleOption[object]] = {option.name: option for option in rule.options}
    for option in rule.options:
        _validate_option_declaration(rule=rule, option=option)
    unknown: set[str] = set(configured) - set(declarations)
    if unknown:
        raise RulesError(f"rule {rule.code} has unknown options: {', '.join(sorted(unknown))}")
    for name, value in configured.items():
        option: RuleOption[object] = declarations[name]
        expected: type[object] = option.value_type
        if expected is tuple:
            valid: bool = isinstance(value, tuple)
        else:
            valid = isinstance(value, expected) and not (
                expected is int and isinstance(value, bool)
            )
        if not valid:
            raise RulesError(f"rule {rule.code} option {name} has the wrong type")
        if option.choices and value not in option.choices:
            raise RulesError(f"rule {rule.code} option {name} is not an allowed choice")
        if isinstance(value, tuple):
            if option.minimum_items is not None and len(value) < option.minimum_items:
                raise RulesError(f"rule {rule.code} option {name} has too few items")
            expected_item_type: type[object] | None = option.item_type
            if expected_item_type is not None and any(
                not isinstance(item, expected_item_type) for item in value
            ):
                raise RulesError(
                    f"rule {rule.code} option {name} has item values of the wrong type"
                )
        if isinstance(value, int) and not isinstance(value, bool):
            if option.minimum is not None and value < option.minimum:
                raise RulesError(f"rule {rule.code} option {name} is below its minimum")
            if option.maximum is not None and value > option.maximum:
                raise RulesError(f"rule {rule.code} option {name} exceeds its maximum")


def _validate_option_declaration(*, rule: Rule, option: RuleOption[object]) -> None:
    if not option.name.strip() or not option.description.strip():
        raise RulesError(f"rule {rule.code} declares an incomplete option")
    default: object = option.default
    expected: type[object] = option.value_type
    valid_default: bool = isinstance(default, expected) and not (
        expected is int and isinstance(default, bool)
    )
    if not valid_default:
        raise RulesError(f"rule {rule.code} option {option.name} has a default of the wrong type")
    if option.choices and default not in option.choices:
        raise RulesError(f"rule {rule.code} option {option.name} default is not an allowed choice")
    if isinstance(default, tuple):
        if option.minimum_items is not None and len(default) < option.minimum_items:
            raise RulesError(f"rule {rule.code} option {option.name} default has too few items")
        if option.item_type is not None and any(
            not isinstance(item, option.item_type) for item in default
        ):
            raise RulesError(
                f"rule {rule.code} option {option.name} default has items of the wrong type"
            )
    if isinstance(default, int) and not isinstance(default, bool):
        if option.minimum is not None and default < option.minimum:
            raise RulesError(f"rule {rule.code} option {option.name} default is below its minimum")
        if option.maximum is not None and default > option.maximum:
            raise RulesError(f"rule {rule.code} option {option.name} default exceeds its maximum")
