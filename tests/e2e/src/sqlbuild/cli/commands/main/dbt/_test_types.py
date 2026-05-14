from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbtExecutionQueryAssertion:
    description: str
    sql: str
    expected_rows: tuple[tuple[object, ...], ...]


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


@dataclass(frozen=True)
class DbtExecutionCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_row_counts: tuple[tuple[str, int], ...]
    unexpected_relations: tuple[str, ...] = ()
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_absent_stdout_fragments: tuple[str, ...] = ()
    expected_query_assertions: tuple[DbtExecutionQueryAssertion, ...] = ()
    expected_planned_sqlbuild_models: tuple[str, ...] | None = None
    rerun_count: int = 1


@dataclass(frozen=True)
class DbtExecutionFailureCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtTestCliTestCase:
    description: str
    command: tuple[str, ...]
    setup_command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...] = ()
    expected_query_assertions: tuple[DbtExecutionQueryAssertion, ...] = ()


@dataclass(frozen=True)
class DbtScenarioCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtDebugCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_returncode: int = 0
