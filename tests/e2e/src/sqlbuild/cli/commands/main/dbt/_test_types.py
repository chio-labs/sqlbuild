from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbtPlanCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_selected_models: tuple[str, ...]
    expected_dbt_skipped: bool
    expected_sqlbuild_skipped: bool
    expected_anchor_terms: tuple[str, ...] = ()
    expected_path_translations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DbtPlanRelativeProjectDirTestCase:
    description: str
    command: tuple[str, ...]
    expected_project_dir: Path
    expected_selected_models: tuple[str, ...]


@dataclass(frozen=True)
class DbtPlanHumanCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtPlanErrorCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]
