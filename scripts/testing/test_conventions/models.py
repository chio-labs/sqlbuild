"""Structured runtime models for test convention checks."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Violation:
    """A single test convention violation."""

    code: str
    path: Path
    message: str
    line: int | None = None

    def format(self, repo_root: Path) -> str:
        """Render the violation in a stable CLI-friendly format."""

        relative_path: Path = self.path.relative_to(repo_root)
        if self.line is None:
            return f"{relative_path}: {self.code} {self.message}"
        return f"{relative_path}:{self.line}: {self.code} {self.message}"


@dataclass(frozen=True, slots=True)
class LocalTestTypesInfo:
    """Metadata extracted from a local _test_types.py file."""

    module_name: str
    dataclass_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class ModuleContext:
    """Precomputed module metadata used by test checks."""

    imported_local_test_case_types: frozenset[str]
    test_case_annotation_names: frozenset[str]
    module_level_case_lists: dict[str, ast.expr]
