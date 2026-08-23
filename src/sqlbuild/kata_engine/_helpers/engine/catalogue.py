"""Built-in and custom kata rule catalogue construction."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import sys
from collections.abc import Mapping
from dataclasses import replace
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild.kata_engine._helpers.engine.definition import rule_from_value
from sqlbuild.kata_engine._helpers.engine.native import native_catalogue, native_selected_codes
from sqlbuild.kata_engine.constants import KATA_DECORATOR_TOKEN
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig, KataFault, KataRule, RuleOption


def build_catalogue(*, config: KataConfig, project_dir: Path) -> tuple[KataRule, ...]:
    """Build and validate the complete configured rule catalogue."""

    custom: tuple[KataRule, ...] = (
        *_load_modules(names=config.rule_modules, project_dir=project_dir),
        *_load_paths(paths=config.rule_paths, project_dir=project_dir),
    )
    rules: tuple[KataRule, ...] = (*_builtins(), *custom)
    codes: tuple[str, ...] = tuple(rule.code for rule in rules)
    duplicates: tuple[str, ...] = tuple(
        sorted(code for code in set(codes) if codes.count(code) > 1)
    )
    if duplicates:
        raise KataError(f"duplicate kata rule codes: {', '.join(duplicates)}")
    for rule in rules:
        _validate_options(rule=rule, configured=config.rule_options.get(rule.code, {}))
    configured_codes: set[str] = set(config.rule_options)
    unknown_option_codes: set[str] = configured_codes - set(codes)
    if unknown_option_codes:
        raise KataError(
            f"rule options target unknown codes: {', '.join(sorted(unknown_option_codes))}"
        )
    return tuple(sorted(rules, key=lambda item: item.code))


def _builtins() -> tuple[KataRule, ...]:
    return tuple(
        KataRule(
            code=str(item["code"]),
            family=str(item["family"]),
            slug=str(item["slug"]),
            message=str(item["message"]),
            remediation=str(item["remediation"]),
            check=_native_builtin,
            enabled_by_default=bool(item["enabled_by_default"]),
            project_wide=bool(item["project_wide"]),
        )
        for item in native_catalogue()
    )


def _native_builtin(*, model: object, ctx: object) -> list[KataFault]:
    del model, ctx
    raise KataError("built-in kata rules execute only through the native engine")


def select_rules(*, catalogue: tuple[KataRule, ...], config: KataConfig) -> tuple[KataRule, ...]:
    """Resolve the active catalogue through the native Fensu policy owner."""

    by_code: dict[str, KataRule] = {rule.code: rule for rule in catalogue}
    codes: tuple[str, ...] = native_selected_codes(config=config, catalogue=catalogue)
    try:
        return tuple(by_code[code] for code in codes)
    except KeyError as error:
        raise KataError(f"native kata policy returned unknown rule {error.args[0]}") from error


def _load_modules(*, names: tuple[str, ...], project_dir: Path) -> tuple[KataRule, ...]:
    result: list[KataRule] = []
    repository_path: str = str(project_dir.resolve())
    existing_modules: frozenset[str] = frozenset(sys.modules)
    sys.path.insert(0, repository_path)
    try:
        for name in names:
            try:
                module: ModuleType = importlib.import_module(name)
            except Exception as error:
                raise KataError(f"could not import kata rule module {name}: {error}") from error
            source: str | None = inspect.getsourcefile(module)
            if source is None or not Path(source).resolve().is_relative_to(project_dir.resolve()):
                raise KataError(f"kata rule module {name} must be repository-owned")
            result.extend(_module_rules(module=module, source=Path(source)))
    finally:
        sys.path.remove(repository_path)
        _remove_loaded_project_modules(
            existing_modules=existing_modules,
            project_dir=project_dir,
        )
    return tuple(result)


def _load_paths(*, paths: tuple[str, ...], project_dir: Path) -> tuple[KataRule, ...]:
    result: list[KataRule] = []
    existing_modules: frozenset[str] = frozenset(sys.modules)
    repository_path: str = str(project_dir.resolve())
    sys.path.insert(0, repository_path)
    try:
        for configured in paths:
            path: Path = (project_dir / configured).resolve()
            if not path.is_relative_to(project_dir.resolve()):
                raise KataError(f"kata rule path escapes the project: {configured}")
            configured_directory: bool = path.is_dir()
            files: tuple[Path, ...] = (
                tuple(sorted(path.rglob("*.py"))) if path.is_dir() else (path,)
            )
            for file_path in files:
                if not file_path.is_file():
                    raise KataError(f"kata rule path does not exist: {file_path}")
                if configured_directory and KATA_DECORATOR_TOKEN not in file_path.read_text(
                    encoding="utf-8"
                ):
                    continue
                digest: str = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
                name: str = f"sqlbuild._loaded_kata.{digest}"
                spec: ModuleSpec | None = importlib.util.spec_from_file_location(name, file_path)
                if spec is None or spec.loader is None:
                    raise KataError(f"could not load kata rule file {file_path}")
                module: ModuleType = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception as error:
                    raise KataError(
                        f"could not import kata rule file {file_path}: {error}"
                    ) from error
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


def _module_rules(
    *, module: ModuleType, source: Path, require_rules: bool = True
) -> tuple[KataRule, ...]:
    rules: tuple[KataRule, ...] = tuple(
        rule
        for value in vars(module).values()
        if getattr(value, "__module__", None) == module.__name__
        and (rule := rule_from_value(value=value)) is not None
    )
    if not rules and require_rules:
        raise KataError(f"kata rule source exposes no @kata rules: {source}")
    return tuple(replace(rule, source=source.as_posix()) for rule in rules)


def _remove_loaded_project_modules(*, existing_modules: frozenset[str], project_dir: Path) -> None:
    for name in tuple(sys.modules):
        if name in existing_modules:
            continue
        module: object = sys.modules.get(name)
        source: object = getattr(module, "__file__", None)
        if isinstance(source, str) and Path(source).resolve().is_relative_to(project_dir.resolve()):
            _ = sys.modules.pop(name, None)


def _validate_options(*, rule: KataRule, configured: Mapping[str, object]) -> None:
    declarations: dict[str, RuleOption[object]] = {option.name: option for option in rule.options}
    for option in rule.options:
        _validate_option_declaration(rule=rule, option=option)
    unknown: set[str] = set(configured) - set(declarations)
    if unknown:
        raise KataError(f"rule {rule.code} has unknown options: {', '.join(sorted(unknown))}")
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
            raise KataError(f"rule {rule.code} option {name} has the wrong type")
        if option.choices and value not in option.choices:
            raise KataError(f"rule {rule.code} option {name} is not an allowed choice")
        if isinstance(value, tuple):
            if option.minimum_items is not None and len(value) < option.minimum_items:
                raise KataError(f"rule {rule.code} option {name} has too few items")
            expected_item_type: type[object] | None = option.item_type
            if expected_item_type is not None and any(
                not isinstance(item, expected_item_type) for item in value
            ):
                raise KataError(f"rule {rule.code} option {name} has item values of the wrong type")
        if isinstance(value, int) and not isinstance(value, bool):
            if option.minimum is not None and value < option.minimum:
                raise KataError(f"rule {rule.code} option {name} is below its minimum")
            if option.maximum is not None and value > option.maximum:
                raise KataError(f"rule {rule.code} option {name} exceeds its maximum")


def _validate_option_declaration(*, rule: KataRule, option: RuleOption[object]) -> None:
    if not option.name.strip() or not option.description.strip():
        raise KataError(f"rule {rule.code} declares an incomplete option")
    default: object = option.default
    expected: type[object] = option.value_type
    valid_default: bool = isinstance(default, expected) and not (
        expected is int and isinstance(default, bool)
    )
    if not valid_default:
        raise KataError(f"rule {rule.code} option {option.name} has a default of the wrong type")
    if option.choices and default not in option.choices:
        raise KataError(f"rule {rule.code} option {option.name} default is not an allowed choice")
    if isinstance(default, tuple):
        if option.minimum_items is not None and len(default) < option.minimum_items:
            raise KataError(f"rule {rule.code} option {option.name} default has too few items")
        if option.item_type is not None and any(
            not isinstance(item, option.item_type) for item in default
        ):
            raise KataError(
                f"rule {rule.code} option {option.name} default has items of the wrong type"
            )
    if isinstance(default, int) and not isinstance(default, bool):
        if option.minimum is not None and default < option.minimum:
            raise KataError(f"rule {rule.code} option {option.name} default is below its minimum")
        if option.maximum is not None and default > option.maximum:
            raise KataError(f"rule {rule.code} option {option.name} default exceeds its maximum")
