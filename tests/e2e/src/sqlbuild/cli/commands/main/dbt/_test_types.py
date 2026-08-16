from __future__ import annotations

from collections.abc import Callable
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
    setup: Callable[[Path], None]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_returncode: int = 1
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
class DbtDebugCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_returncode: int = 0


@dataclass(frozen=True)
class DbtInitDuckDbE2ETestCase:
    description: str
    expected_generated_files: tuple[str, ...]
    unexpected_generated_paths: tuple[str, ...]
    expected_toml_fragments: tuple[str, ...]
    unexpected_toml_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_dbt_stdout_fragments: tuple[str, ...]
    expected_dbt_fingerprint_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtInitInteractiveE2ETestCase:
    description: str
    input_text: str
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtAutoInitE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]
    expected_toml_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtCliFlagAmbiguityE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtInitMissingProdRelationBuildE2ETestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtInitDetectedReuseRefE2ETestCase:
    description: str
    production_ref: str
    expected_config_git_ref: str
    unexpected_stdout_fragments: tuple[str, ...]
