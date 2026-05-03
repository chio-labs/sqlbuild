"""Orchestration and CLI for test convention checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.testing.test_conventions.filesystem import (
    discover_test_directories,
    iter_python_files,
    resolve_repo_root,
)
from scripts.testing.test_conventions.models import LocalTestTypesInfo, Violation
from scripts.testing.test_conventions.rules import (
    build_module_context,
    check_init_module,
    check_no_relative_imports,
    check_scenario_models_file,
    check_test_directory_path,
    check_test_file,
    check_test_types_file,
    parse_python_module,
)


def check_paths(paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Run test convention checks for the provided paths."""

    target_paths: list[Path] = (
        [path.resolve() for path in paths] if paths else [Path("tests").resolve()]
    )
    actual_repo_root: Path = (
        repo_root.resolve() if repo_root is not None else resolve_repo_root(target_paths)
    )
    python_files: list[Path] = iter_python_files(target_paths)
    test_directories: list[Path] = discover_test_directories(python_files)

    violations: list[Violation] = []
    local_test_types_by_directory: dict[Path, LocalTestTypesInfo] = {}
    parsed_modules: dict[Path, object] = {}

    for file_path in python_files:
        parsed_modules[file_path] = parse_python_module(file_path)

    for test_directory in test_directories:
        violations.extend(check_test_directory_path(actual_repo_root, test_directory))

        test_types_path: Path = test_directory / "_test_types.py"
        if not test_types_path.exists():
            violations.append(
                Violation(
                    code="TC026",
                    path=test_directory,
                    line=None,
                    message=(
                        "test directories containing test_*.py must include a local _test_types.py"
                    ),
                )
            )
            continue

        module: object | None = parsed_modules.get(test_types_path)
        if module is None:
            module = parse_python_module(test_types_path)
            parsed_modules[test_types_path] = module

        test_types_info, test_types_violations = check_test_types_file(
            actual_repo_root,
            test_types_path,
            module,
        )
        local_test_types_by_directory[test_directory] = test_types_info
        violations.extend(test_types_violations)

    for file_path, module in parsed_modules.items():
        if not _is_in_test_directory(file_path, test_directories):
            continue

        violations.extend(check_no_relative_imports(file_path, module))

        if file_path.name == "__init__.py":
            violations.extend(check_init_module(actual_repo_root, file_path, module))
            continue

        if file_path.name == "_test_types.py":
            continue

        if file_path.name == "scenario_models.py":
            violations.extend(check_scenario_models_file(file_path, module))
            continue

        if not file_path.name.endswith(".py") or not file_path.name.startswith("test_"):
            continue

        local_test_types: LocalTestTypesInfo | None = local_test_types_by_directory.get(
            file_path.parent
        )
        if local_test_types is None:
            continue

        context, context_violations = build_module_context(
            actual_repo_root,
            file_path,
            module,
            local_test_types,
        )
        violations.extend(context_violations)
        violations.extend(check_test_file(file_path, module, local_test_types, context))

    return sorted(
        violations,
        key=lambda violation: (str(violation.path), violation.line or 0, violation.code),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="check_test_conventions")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("tests")])
    args: argparse.Namespace = parser.parse_args(argv)

    violations: list[Violation] = check_paths(args.paths)
    repo_root: Path = resolve_repo_root([path.resolve() for path in args.paths])

    for violation in violations:
        print(violation.format(repo_root), file=sys.stderr)

    return 1 if violations else 0


def _is_in_test_directory(file_path: Path, test_directories: list[Path]) -> bool:
    return any(parent == file_path.parent for parent in test_directories)
