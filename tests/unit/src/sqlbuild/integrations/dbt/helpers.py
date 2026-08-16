from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
)
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.integrations.dbt._helpers.cli.runner import build_dbt_ls_argv
from sqlbuild.integrations.dbt._helpers.graph.core import (
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliConfigOverrides,
    DbtCliOptions,
    DbtCombinedGraphKey,
    DbtCommandResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def _build_present_field(name: str, value: object) -> dict[str, object]:
    return {name: value}


def _build_absent_field(name: str, value: object) -> dict[str, object]:
    del name, value
    return {}


_OPTIONAL_FIELD_BUILDERS: MappingProxyType[bool, Callable[[str, object], dict[str, object]]] = (
    MappingProxyType(
        {
            True: _build_present_field,
            False: _build_absent_field,
        }
    )
)


def build_cli_overrides(
    *,
    project_dir: str | None = None,
    profiles_dir: str | None = None,
    target: str | None = None,
    target_path: str | None = None,
) -> DbtCliConfigOverrides:
    """Build dbt CLI config overrides for tests."""

    return DbtCliConfigOverrides(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        target=target,
        target_path=target_path,
    )


def build_dbt_cli_options(project_root: Path) -> DbtCliOptions:
    """Build representative dbt options for argv tests."""

    return DbtCliOptions(
        project_dir=project_root / "dbt",
        profiles_dir=project_root / "profiles",
        target="prod",
        target_path=project_root / "target/dbt",
        vars='{"run_date":"2026-01-01"}',
        state=project_root / "state",
        defer=True,
    )


class RecordingDbtInvoker:
    """Record dbt invocations and return a fixed result."""

    def __init__(self, result: DbtCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        self.calls.append((argv, cwd))
        return self.result


class MappingDbtInvoker:
    """Record dbt invocations and return results by argv."""

    def __init__(self, results_by_argv: dict[tuple[str, ...], DbtCommandResult]) -> None:
        self.results_by_argv = results_by_argv
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        self.calls.append((argv, cwd))
        return self.results_by_argv.get(
            argv,
            DbtCommandResult(argv=argv, returncode=0, stdout=""),
        )


class CompileOnlyDbtRunner(DbtRunner):
    """Minimal dbt runner for execution-pipeline tests that only compile."""

    def __init__(self) -> None:
        self.compile_full_refresh_values: list[bool] = []

    def compile(self, *, options: DbtCliOptions, full_refresh: bool = False) -> DbtCommandResult:
        del options
        self.compile_full_refresh_values.append(full_refresh)
        return DbtCommandResult(argv=("dbt", "compile"), returncode=0)


def build_dbt_ls_command_result(
    *, argv: tuple[str, ...], unique_ids: tuple[str, ...]
) -> DbtCommandResult:
    """Build a dbt ls command result with JSON-lines nodes."""

    stdout: str = "\n".join(json.dumps({"unique_id": unique_id}) for unique_id in unique_ids)
    return DbtCommandResult(argv=argv, returncode=0, stdout=stdout)


def _build_sqlbuild_model_plan_entry(model_name: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=model_name,
        ),
        name=model_name,
        relative_path=Path(f"models/{model_name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.NO_CHANGE,
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=model_name,
            qualified_name=None,
        ),
        fingerprint_query_sql="select 1",
        resolved_sql="select 1",
        logical_ddl="",
        backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
    )


def build_dbt_plan_mapping_invoker(
    *,
    options: DbtCliOptions,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    full_dbt_ls_unique_ids: tuple[str, ...],
    anchor_dbt_ls_unique_ids_by_term: dict[str, tuple[str, ...]],
) -> MappingDbtInvoker:
    """Build a mapping invoker for plan orchestration dbt ls calls."""

    results_by_argv: dict[tuple[str, ...], DbtCommandResult] = {}
    full_argv: tuple[str, ...] = build_dbt_ls_argv(
        dbt_executable="dbt",
        options=options,
        select=select,
        exclude=exclude,
    )
    results_by_argv[full_argv] = build_dbt_ls_command_result(
        argv=full_argv,
        unique_ids=full_dbt_ls_unique_ids,
    )
    term: str
    unique_ids: tuple[str, ...]
    for term, unique_ids in anchor_dbt_ls_unique_ids_by_term.items():
        anchor_argv: tuple[str, ...] = build_dbt_ls_argv(
            dbt_executable="dbt",
            options=options,
            select=(term,),
            exclude=exclude,
        )
        results_by_argv[anchor_argv] = build_dbt_ls_command_result(
            argv=anchor_argv,
            unique_ids=unique_ids,
        )
    return MappingDbtInvoker(results_by_argv=results_by_argv)


def extract_dbt_ls_selects(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Extract select terms from a dbt ls argv for assertions."""

    return _extract_dbt_option_values(argv=argv, option="--select")


def extract_dbt_ls_excludes(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Extract exclude terms from a dbt ls argv for assertions."""

    return _extract_dbt_option_values(argv=argv, option="--exclude")


def _extract_dbt_option_values(*, argv: tuple[str, ...], option: str) -> tuple[str, ...]:
    command: str = " ".join(argv)
    pattern: str = rf"(?:^| ){re.escape(option)}((?: (?!--)\S+)*)"
    match: re.Match[str] = cast(
        re.Match[str], re.search(pattern, command) or re.match(r"()", command)
    )
    return tuple(match.group(1).split())


def build_manifest_data(
    *,
    nodes: tuple[dict[str, object], ...],
    sources: tuple[dict[str, object], ...] = (),
    macros: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    """Build a minimal dbt manifest payload for model lookup tests."""

    return {
        "nodes": {str(node["unique_id"]): node for node in nodes},
        "sources": {str(source["unique_id"]): source for source in sources},
        "macros": {str(macro["unique_id"]): macro for macro in macros},
    }


def build_manifest_model_node(
    *,
    unique_id: str,
    package_name: str,
    name: str,
    relation_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    alias: str | None = None,
    checksum: str | None = None,
    fqn: tuple[str, ...] = (),
    raw_code: str | None = None,
    compiled_code: str | None = None,
    depends_on_nodes: tuple[str, ...] = (),
    depends_on_macro_ids: tuple[str, ...] = (),
    resource_type: str = "model",
    materialized: str | None = "view",
    incremental_strategy: str | None = None,
    meta: dict[str, object] | None = None,
    config_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a minimal dbt manifest model node."""

    resolved_raw_codes: dict[bool, str] = {
        True: f"select * from {name}",
        False: cast(str, raw_code),
    }
    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": resource_type,
        "package_name": package_name,
        "name": name,
        "raw_code": resolved_raw_codes[raw_code is None],
    }
    optional_fields: tuple[tuple[str, object, bool], ...] = (
        ("relation_name", relation_name, relation_name is not None),
        ("compiled_code", compiled_code, compiled_code is not None),
        ("database", database, database is not None),
        ("schema", schema, schema is not None),
        ("alias", alias, alias is not None),
        ("checksum", {"checksum": checksum}, checksum is not None),
        ("fqn", list(fqn), bool(fqn)),
        (
            "depends_on",
            {
                "nodes": list(depends_on_nodes),
                "macros": list(depends_on_macro_ids),
            },
            bool(depends_on_nodes or depends_on_macro_ids),
        ),
    )
    field_name: str
    field_value: object
    is_present: bool
    for field_name, field_value, is_present in optional_fields:
        node.update(_OPTIONAL_FIELD_BUILDERS[is_present](field_name, field_value))
    config: dict[str, object] = {"materialized": materialized}
    config.update(
        _OPTIONAL_FIELD_BUILDERS[incremental_strategy is not None](
            "incremental_strategy", incremental_strategy
        )
    )
    config.update(_OPTIONAL_FIELD_BUILDERS[meta is not None]("meta", meta))
    config.update(config_overrides or {})
    node.update(_OPTIONAL_FIELD_BUILDERS[materialized is not None]("config", config))
    return node


def build_manifest_source_node(
    *,
    unique_id: str,
    package_name: str = "analytics",
    source_name: str = "raw",
    name: str = "orders",
    relation_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    identifier: str | None = None,
    loaded_at_field: str | None = None,
    loaded_at_query: str | None = None,
    freshness: dict[str, object] | None = None,
    freshness_filter: str | None = None,
) -> dict[str, object]:
    """Build a minimal dbt manifest source node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "source",
        "package_name": package_name,
        "source_name": source_name,
        "name": name,
    }
    optional_fields: tuple[tuple[str, object, bool], ...] = (
        ("relation_name", relation_name, relation_name is not None),
        ("database", database, database is not None),
        ("schema", schema, schema is not None),
        ("identifier", identifier, identifier is not None),
        ("loaded_at_field", loaded_at_field, loaded_at_field is not None),
        ("loaded_at_query", loaded_at_query, loaded_at_query is not None),
        ("freshness", freshness, freshness is not None),
        ("filter", freshness_filter, freshness_filter is not None),
    )
    field_name: str
    field_value: object
    is_present: bool
    for field_name, field_value, is_present in optional_fields:
        node.update(_OPTIONAL_FIELD_BUILDERS[is_present](field_name, field_value))
    return node


def build_manifest_seed_node(
    *,
    unique_id: str,
    package_name: str = "analytics",
    name: str = "countries",
    relation_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    alias: str | None = None,
    checksum: str | None = None,
    config_overrides: dict[str, object] | None = None,
    root_path: str | None = None,
    original_file_path: str | None = None,
) -> dict[str, object]:
    """Build a minimal dbt manifest seed node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "seed",
        "package_name": package_name,
        "name": name,
    }
    optional_fields: tuple[tuple[str, object, bool], ...] = (
        ("relation_name", relation_name, relation_name is not None),
        ("database", database, database is not None),
        ("schema", schema, schema is not None),
        ("alias", alias, alias is not None),
        ("checksum", {"checksum": checksum}, checksum is not None),
        ("config", config_overrides, config_overrides is not None),
        ("root_path", root_path, root_path is not None),
        ("original_file_path", original_file_path, original_file_path is not None),
    )
    field_name: str
    field_value: object
    is_present: bool
    for field_name, field_value, is_present in optional_fields:
        node.update(_OPTIONAL_FIELD_BUILDERS[is_present](field_name, field_value))
    return node


def build_compiled_project_with_models(sql_by_model_name: dict[str, str]) -> CompiledProject:
    """Build a minimal compiled project from model SQL strings."""

    return build_compiled_project_with_model_specs(
        sql_by_model_name=sql_by_model_name,
        tags_by_model_name={},
        path_by_model_name={},
    )


def build_compiled_project_with_model_specs(
    *,
    sql_by_model_name: dict[str, str],
    tags_by_model_name: dict[str, tuple[str, ...]],
    path_by_model_name: dict[str, str],
) -> CompiledProject:
    """Build a minimal compiled project from model SQL, tags, and relative paths."""

    model_inputs: list[CompileModelInput] = []
    model_name: str
    sql: str
    for model_name, sql in sql_by_model_name.items():
        relative_path: Path = Path(path_by_model_name.get(model_name, f"models/{model_name}.sql"))
        model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
            file_path=Path("/repo") / relative_path,
            relative_path=relative_path,
            contents=f"MODEL ();\n\n{sql}\n",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql=sql,
        )
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=CompileModelConfig(
                    values=_OPTIONAL_FIELD_BUILDERS[model_name in tags_by_model_name](
                        "tags", tags_by_model_name.get(model_name, ())
                    )
                ),
                query_sql=sql,
                references=extract_sql_references(sql),
            )
        )
    return assemble_compiled_project(
        inputs=CompileProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            discovered_inputs=DiscoveredProjectInputs(
                project_config=ProjectConfig(name="demo", adapter="duckdb"),
                local_config=LocalConfig(),
            ),
            model_inputs=tuple(model_inputs),
        )
    )


def graph_edge_stable_ids(
    graph_edges: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> dict[str, tuple[str, ...]]:
    """Render graph edges as stable IDs for assertions."""

    stable_edges: dict[str, tuple[str, ...]] = {}
    for key, deps in graph_edges.items():
        stable_deps: list[str] = []
        for dep in deps:
            stable_deps.append(dep.stable_id)
        stable_edges[key.stable_id] = tuple(stable_deps)
    return stable_edges


def graph_key_stable_ids(keys: frozenset[DbtCombinedGraphKey]) -> tuple[str, ...]:
    """Render graph keys as sorted stable IDs for assertions."""

    return tuple(sorted(key.stable_id for key in keys))


def graph_key_from_stable_id(stable_id: str) -> DbtCombinedGraphKey:
    """Build a graph key from its stable string form."""

    owner, resource_type, name = stable_id.split(":", maxsplit=2)
    owner_enum: DbtCombinedGraphOwner = DbtCombinedGraphOwner(owner)
    resource_type_enum: DbtCombinedGraphResourceType = DbtCombinedGraphResourceType(resource_type)
    factories: dict[
        tuple[DbtCombinedGraphOwner, DbtCombinedGraphResourceType],
        Callable[[str], DbtCombinedGraphKey],
    ] = {
        (
            DbtCombinedGraphOwner.DBT,
            DbtCombinedGraphResourceType.SOURCE,
        ): dbt_source_graph_key,
        (
            DbtCombinedGraphOwner.DBT,
            DbtCombinedGraphResourceType.MODEL,
        ): dbt_model_graph_key,
        (
            DbtCombinedGraphOwner.SQLBUILD,
            DbtCombinedGraphResourceType.MODEL,
        ): sqlbuild_model_graph_key,
    }
    return factories[(owner_enum, resource_type_enum)](name)
