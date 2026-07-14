"""Collect test convention violations for selected paths."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.testing._helpers.filesystem import (
    collect_python_files,
    discover_test_directories,
    resolve_repo_root,
)
from scripts.testing._helpers.rules import (
    build_module_context,
    check_init_module,
    check_no_relative_imports,
    check_scenario_models_file,
    check_test_directory_path,
    check_test_file,
    check_test_types_file,
    parse_python_module,
)
from scripts.testing.constants import (
    INIT_MODULE_FILENAME,
    SCENARIO_MODELS_FILENAME,
    TEST_TYPES_FILENAME,
)
from scripts.testing.models import LocalTestTypesInfo, Violation


def collect_violations(*, paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Collect test convention violations for the provided paths."""

    target_paths: list[Path] = (
        [path.resolve() for path in paths] if paths else [Path("tests").resolve()]
    )
    actual_repo_root: Path = (
        repo_root.resolve() if repo_root is not None else resolve_repo_root(target_paths)
    )
    python_files: list[Path] = collect_python_files(target_paths)
    test_directories: list[Path] = discover_test_directories(python_files)

    violations: list[Violation] = []
    local_test_types_by_directory: dict[Path, LocalTestTypesInfo] = {}
    parsed_modules: dict[Path, ast.Module] = {}

    for file_path in python_files:
        parsed_modules[file_path] = parse_python_module(file_path)

    for test_directory in test_directories:
        violations.extend(
            check_test_directory_path(repo_root=actual_repo_root, test_directory=test_directory)
        )

        test_types_path: Path = test_directory / TEST_TYPES_FILENAME
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

        module: ast.Module | None = parsed_modules.get(test_types_path)
        if module is None:
            module = parse_python_module(test_types_path)
            parsed_modules[test_types_path] = module

        test_types_info, test_types_violations = check_test_types_file(
            repo_root=actual_repo_root,
            file_path=test_types_path,
            module=module,
        )
        local_test_types_by_directory[test_directory] = test_types_info
        violations.extend(test_types_violations)

    for file_path, module in parsed_modules.items():
        if not _is_in_test_directory(file_path=file_path, test_directories=test_directories):
            continue

        violations.extend(check_no_relative_imports(file_path=file_path, module=module))

        if file_path.name == INIT_MODULE_FILENAME:
            violations.extend(
                check_init_module(repo_root=actual_repo_root, file_path=file_path, module=module)
            )
            continue

        if file_path.name == TEST_TYPES_FILENAME:
            continue

        if file_path.name == SCENARIO_MODELS_FILENAME:
            violations.extend(check_scenario_models_file(file_path=file_path, module=module))
            continue

        if not file_path.name.endswith(".py") or not file_path.name.startswith("test_"):
            continue

        local_test_types: LocalTestTypesInfo | None = local_test_types_by_directory.get(
            file_path.parent
        )
        if local_test_types is None:
            continue

        context, context_violations = build_module_context(
            repo_root=actual_repo_root,
            file_path=file_path,
            module=module,
            local_test_types=local_test_types,
        )
        violations.extend(context_violations)
        violations.extend(
            check_test_file(
                file_path=file_path,
                module=module,
                local_test_types=local_test_types,
                context=context,
            )
        )

    return sorted(
        violations,
        key=lambda violation: (str(violation.path), violation.line or 0, violation.code),
    )


def _is_in_test_directory(*, file_path: Path, test_directories: list[Path]) -> bool:
    return any(parent == file_path.parent for parent in test_directories)
