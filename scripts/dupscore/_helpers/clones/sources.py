"""Collect clone units from the Python package and Rust crates in the worktree."""

from __future__ import annotations

from pathlib import Path

from scripts.dupscore._helpers.clones.python_units import extract_python_units
from scripts.dupscore._helpers.clones.rust_units import extract_rust_units
from scripts.dupscore.constants import (
    LANGUAGE_PYTHON,
    LANGUAGE_RUST,
    PROJECT_PACKAGE,
    PYTHON_TEST_ROOT,
    RUST_CRATES_ROOT,
    RUST_SOURCE_DIRECTORY,
    RUST_TEST_DIRECTORIES,
    SOURCE_ROOT,
)
from scripts.dupscore.models import CloneUnit, RustFileUnits

_PYTHON_PATTERN: str = "*.py"
_RUST_PATTERN: str = "*.rs"
_CRATE_DIRECTORY_INDEX: int = 1


def collect_clone_units(
    *,
    repo_root: Path,
    languages: tuple[str, ...],
    include_tests: bool,
) -> list[CloneUnit]:
    """Extract units for the requested languages in deterministic path order."""

    units: list[CloneUnit] = []
    if LANGUAGE_PYTHON in languages:
        units.extend(_python_units(repo_root=repo_root, include_tests=include_tests))
    if LANGUAGE_RUST in languages:
        units.extend(_rust_units(repo_root=repo_root, include_tests=include_tests))
    return units


def _python_units(*, repo_root: Path, include_tests: bool) -> list[CloneUnit]:
    files: list[Path] = sorted((repo_root / SOURCE_ROOT / PROJECT_PACKAGE).rglob(_PYTHON_PATTERN))
    if include_tests:
        files.extend(sorted((repo_root / PYTHON_TEST_ROOT).rglob(_PYTHON_PATTERN)))
    units: list[CloneUnit] = []
    for path in files:
        units.extend(
            extract_python_units(
                relative_path=path.relative_to(repo_root).as_posix(),
                source=path.read_text(encoding="utf-8", errors="replace"),
            )
        )
    return units


def _rust_units(*, repo_root: Path, include_tests: bool) -> list[CloneUnit]:
    crates_root: Path = repo_root / RUST_CRATES_ROOT
    files: list[Path] = sorted(
        path
        for path in crates_root.rglob(_RUST_PATTERN)
        if _is_rust_candidate(path=path.relative_to(crates_root), include_tests=include_tests)
    )
    units: list[CloneUnit] = []
    test_prefixes: list[str] = []
    for path in files:
        extracted: RustFileUnits = extract_rust_units(
            relative_path=path.relative_to(repo_root).as_posix(),
            source=path.read_text(encoding="utf-8", errors="replace"),
            include_tests=include_tests,
        )
        units.extend(extracted.units)
        test_prefixes.extend(extracted.test_module_prefixes)
    prefixes: tuple[str, ...] = tuple(test_prefixes)
    return [unit for unit in units if not unit.path.startswith(prefixes)]


def _is_rust_candidate(*, path: Path, include_tests: bool) -> bool:
    parts: tuple[str, ...] = path.parts
    if len(parts) <= _CRATE_DIRECTORY_INDEX:
        return False
    section: str = parts[_CRATE_DIRECTORY_INDEX]
    if include_tests:
        return section == RUST_SOURCE_DIRECTORY or section in RUST_TEST_DIRECTORIES
    nested: tuple[str, ...] = parts[_CRATE_DIRECTORY_INDEX + 1 :]
    return section == RUST_SOURCE_DIRECTORY and not RUST_TEST_DIRECTORIES.intersection(nested)
