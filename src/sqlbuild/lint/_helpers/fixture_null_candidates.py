"""Cheap source scan for contract-aware fixture formatting candidates."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.lint.models import FixtureNullCandidateScan

_FIXTURE_TYPED_NULL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)", re.IGNORECASE
)
_FIXTURE_CTE_MARKERS: tuple[str, ...] = ("__ref__", "__source__", "__seed__")
_IGNORED_SEARCH_DIRECTORIES: frozenset[str] = frozenset({".git", ".venv", "target", "node_modules"})
_MODEL_FIXTURE_PATTERN: re.Pattern[str] = re.compile(
    r"\b__ref__(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(",
    re.IGNORECASE,
)


def has_fixture_typed_null_candidates(*, project_dir: Path) -> bool:
    """Return whether source files may contain safe fixture-null autofixes."""

    return bool(scan_fixture_typed_null_candidates(project_dir=project_dir).paths)


def scan_fixture_typed_null_candidates(
    *, project_dir: Path, selected_paths: frozenset[Path] | None = None
) -> FixtureNullCandidateScan:
    """Return selected SQL-test paths and model names with possible typed-null fixtures."""

    paths: set[Path] = set()
    model_names: set[str] = set()
    tests_root: Path = project_dir / "tests" / "unit"
    if not tests_root.is_dir():
        return FixtureNullCandidateScan()
    for file_path in tests_root.rglob("*.sql"):
        if any(part in _IGNORED_SEARCH_DIRECTORIES for part in file_path.parts):
            continue
        resolved_path: Path = file_path.resolve()
        if selected_paths is not None and resolved_path not in selected_paths:
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        folded: str = contents.casefold()
        if not any(marker in folded for marker in _FIXTURE_CTE_MARKERS):
            continue
        if _FIXTURE_TYPED_NULL_PATTERN.search(contents) is not None:
            paths.add(resolved_path)
            model_names.update(
                match.group("name") for match in _MODEL_FIXTURE_PATTERN.finditer(contents)
            )
    return FixtureNullCandidateScan(
        paths=frozenset(paths),
        model_names=frozenset(model_names),
    )
