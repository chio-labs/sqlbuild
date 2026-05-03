"""Orchestration and CLI for structure convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.structure.structure_conventions.filesystem import (
    iter_scoped_python_files,
    resolve_repo_root,
)
from scripts.structure.structure_conventions.models import Violation
from scripts.structure.structure_conventions.rules import (
    check_adapter_class_entry_module_shape,
    check_banned_generic_filename,
    check_classes_module_name,
    check_client_module_shape,
    check_constants_module,
    check_constants_outside_constants,
    check_cross_package_internal_imports,
    check_dev_tooling_location,
    check_exception_declarations_outside_exceptions,
    check_helpers_module_name,
    check_helpers_package_structure,
    check_helpers_subpackage_shape,
    check_init_module,
    check_integrations_package_structure,
    check_main_command_package_entry_surface,
    check_main_entry_name_collisions,
    check_main_module_shape,
    check_model_declarations_outside_models,
    check_models_module,
    check_nested_runtime_package_direct_modules,
    check_nested_runtime_package_direct_subpackages,
    check_no_relative_imports,
    check_no_sibling_package_imports,
    check_private_definition_ordering,
    check_shared_package_imports,
    check_shared_package_structure,
    check_top_level_domain_direct_modules,
    check_top_level_domain_role_placement,
    check_type_declarations_outside_types,
    check_types_module,
    parse_python_module,
)


def check_paths(paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Run structure convention checks for the provided paths."""

    target_paths: list[Path] = (
        [path.resolve() for path in paths] if paths else _default_target_paths()
    )
    actual_repo_root: Path = (
        repo_root.resolve() if repo_root is not None else resolve_repo_root(target_paths)
    )
    python_files: list[Path] = iter_scoped_python_files(actual_repo_root, target_paths)

    violations: list[Violation] = []
    for file_path in python_files:
        module: object = parse_python_module(file_path)
        violations.extend(check_no_relative_imports(file_path, module))
        violations.extend(check_dev_tooling_location(actual_repo_root, file_path))
        violations.extend(check_top_level_domain_role_placement(actual_repo_root, file_path))
        violations.extend(check_top_level_domain_direct_modules(actual_repo_root, file_path))
        violations.extend(check_nested_runtime_package_direct_modules(actual_repo_root, file_path))
        violations.extend(
            check_nested_runtime_package_direct_subpackages(actual_repo_root, file_path)
        )
        violations.extend(check_banned_generic_filename(file_path))
        violations.extend(check_helpers_module_name(file_path))
        violations.extend(check_classes_module_name(file_path))
        violations.extend(check_init_module(file_path, module))
        violations.extend(check_main_module_shape(file_path, module))
        violations.extend(check_main_command_package_entry_surface(actual_repo_root, file_path))
        violations.extend(check_main_entry_name_collisions(actual_repo_root, file_path))
        violations.extend(check_types_module(file_path, module))
        violations.extend(check_models_module(file_path, module))
        violations.extend(check_constants_module(file_path, module))
        violations.extend(check_model_declarations_outside_models(file_path, module))
        violations.extend(check_private_definition_ordering(file_path, module))
        violations.extend(check_type_declarations_outside_types(file_path, module))
        violations.extend(check_exception_declarations_outside_exceptions(file_path, module))
        violations.extend(check_constants_outside_constants(file_path, module))
        violations.extend(check_helpers_package_structure(actual_repo_root, file_path))
        violations.extend(check_helpers_subpackage_shape(actual_repo_root, file_path))
        violations.extend(check_shared_package_structure(actual_repo_root, file_path))
        violations.extend(check_integrations_package_structure(actual_repo_root, file_path))
        violations.extend(check_client_module_shape(actual_repo_root, file_path, module))
        violations.extend(
            check_adapter_class_entry_module_shape(actual_repo_root, file_path, module)
        )
        violations.extend(check_no_sibling_package_imports(actual_repo_root, file_path, module))
        violations.extend(check_shared_package_imports(actual_repo_root, file_path, module))
        violations.extend(check_cross_package_internal_imports(actual_repo_root, file_path, module))

    return sorted(
        violations, key=lambda violation: (str(violation.path), violation.line or 0, violation.code)
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="check-structure-conventions")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("src/sqlbuild"), Path("scripts")],
    )
    args: argparse.Namespace = parser.parse_args(argv)

    violations: list[Violation] = check_paths(args.paths)
    repo_root: Path = resolve_repo_root([path.resolve() for path in args.paths])

    for violation in violations:
        print(violation.format(repo_root), file=sys.stderr)

    return 1 if violations else 0


def _default_target_paths() -> list[Path]:
    return [Path("src/sqlbuild").resolve(), Path("scripts").resolve()]
