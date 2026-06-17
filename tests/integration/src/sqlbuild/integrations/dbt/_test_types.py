from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.integrations.dbt.types import DbtInteropSkipReason


@dataclass(frozen=True)
class RealDbtRunnerTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    resource_types: tuple[str, ...]
    expected_unique_ids: tuple[str, ...]


@dataclass(frozen=True)
class RealDbtReuseFromCompileTestCase:
    description: str
    git_ref: str
    override_relative_path: Path
    expected_unique_id: str
    expected_manifest_schema: str
    expected_manifest_sql_fragment: str


@dataclass(frozen=True)
class DbtReuseFromCompileErrorTestCase:
    description: str
    git_ref: str
    command_returncode: int
    command_stdout: str
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtReuseFromCompileSetupErrorTestCase:
    description: str
    setup_kind: str
    expected_error_fragment: str


@dataclass(frozen=True)
class RealDbtManifestCompileTestCase:
    description: str
    sqlbuild_model_sql: str
    expected_compiled_sql: str


@dataclass(frozen=True)
class RealDbtCombinedGraphTestCase:
    description: str
    sqlbuild_model_sql_by_name: dict[str, str]
    expected_downstream_from: str
    expected_downstream_keys: tuple[str, ...]


@dataclass(frozen=True)
class RealDbtInteropPlanTestCase:
    description: str
    args: tuple[str, ...]
    sqlbuild_model_sql_by_relative_path: dict[str, str]
    expected_sqlbuild_model_names: tuple[str, ...]
    expected_sqlbuild_command_argvs: tuple[tuple[str, ...], ...]
    expected_dbt_selected_unique_ids: tuple[str, ...]
    expected_dbt_required_unique_ids: tuple[str, ...]
    expected_dbt_required_selector_terms: tuple[str, ...]
    expected_supplemental_dbt_command_argvs: tuple[tuple[str, ...], ...]
    expected_dbt_anchor_terms: tuple[str, ...]
    expected_dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]]
    expected_dbt_skip_reason: DbtInteropSkipReason | None
    expected_sqlbuild_skip_reason: DbtInteropSkipReason | None
    expected_path_translations: tuple[tuple[str, str], ...] = ()
