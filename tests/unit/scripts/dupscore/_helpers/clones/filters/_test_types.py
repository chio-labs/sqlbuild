from __future__ import annotations

from dataclasses import dataclass

from scripts.dupscore.models import FileChanges


@dataclass(frozen=True)
class ClassifyChangeTestCase:
    description: str
    changes: FileChanges | None
    expected_change: str | None


@dataclass(frozen=True)
class ParseDiffTestCase:
    description: str
    diff_text: str
    expected_changes: dict[str, FileChanges]
