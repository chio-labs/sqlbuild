"""Structured runtime models for structure convention checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Violation:
    """A single structure convention violation."""

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
