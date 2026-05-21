from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadCommandIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    expected_json_staging_relation: str | None = None
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class LoadCommandSelectionErrorTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadCommandEmptySelectionTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandConcurrencyTestCase:
    description: str
    project_files: dict[str, str]
    max_concurrency: int
    expected_connection_count: int
    expected_source_order: tuple[str, ...]
