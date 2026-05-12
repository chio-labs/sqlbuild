from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtCommandResult
from sqlbuild.spec.models.project import DbtConfig


@dataclass(frozen=True)
class DbtConfigResolutionTestCase:
    description: str
    config: DbtConfig
    cli_project_dir: str | None
    cli_profiles_dir: str | None
    cli_target: str | None
    cli_target_path: str | None
    require_project_dir: bool
    expected_project_dir: Path | None
    expected_profiles_dir: Path | None
    expected_target: str | None
    expected_target_path: Path | None


@dataclass(frozen=True)
class DbtConfigErrorTestCase:
    description: str
    config: DbtConfig
    cli_project_dir: str | None
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtArgvTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    resource_types: tuple[str, ...]
    expected_argv: tuple[str, ...]


@dataclass(frozen=True)
class DbtLsParseTestCase:
    description: str
    stdout: str
    expected_unique_ids: tuple[str, ...]
    expected_resource_types: tuple[str | None, ...]


@dataclass(frozen=True)
class DbtRunnerMemoTestCase:
    description: str
    command_result: DbtCommandResult
    expected_call_count: int


@dataclass(frozen=True)
class DbtRunnerCommandTestCase:
    description: str
    command_result: DbtCommandResult
    expected_argv: tuple[str, ...]


@dataclass(frozen=True)
class DbtManifestResolutionTestCase:
    description: str
    manifest_data: dict[str, object]
    package_name: str | None
    model_name: str
    expected_relation_name: str


@dataclass(frozen=True)
class DbtManifestResolutionErrorTestCase:
    description: str
    manifest_data: dict[str, object]
    package_name: str | None
    model_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtCombinedGraphTestCase:
    description: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    expected_upstream_edges: tuple[tuple[str, tuple[str, ...]], ...]
    expected_downstream_from: str
    expected_downstream_keys: tuple[str, ...]
    expected_upstream_from: str
    expected_upstream_keys: tuple[str, ...]
