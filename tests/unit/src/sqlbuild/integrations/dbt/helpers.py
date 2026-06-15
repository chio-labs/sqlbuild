from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.helpers.refs import extract_sql_references
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.integrations.dbt.helpers.graph import (
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner, build_dbt_ls_argv
from sqlbuild.integrations.dbt.models import (
    DbtCliConfigOverrides,
    DbtCliOptions,
    DbtCombinedGraphKey,
    DbtCommandResult,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtCombinedGraphResourceType
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


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
        result: DbtCommandResult | None = self.results_by_argv.get(argv)
        if result is not None:
            return result
        return DbtCommandResult(argv=argv, returncode=0, stdout="")


class CompileOnlyDbtRunner(DbtRunner):
    """Minimal dbt runner for execution-pipeline tests that only compile."""

    def compile(self, *, options: DbtCliOptions) -> DbtCommandResult:
        del options
        return DbtCommandResult(argv=("dbt", "compile"), returncode=0)


def emit_connection_progress(**kwargs: object) -> None:
    """Emit one successful connection progress cycle from a mocked planner."""

    start: object = kwargs["on_connection_start"]
    complete: object = kwargs["on_connection_complete"]
    assert callable(start)
    assert callable(complete)
    on_start: Callable[[int], None] = cast(Callable[[int], None], start)
    on_complete: Callable[[int, float], None] = cast(Callable[[int, float], None], complete)
    on_start(1)
    on_complete(1, 0.0)


def build_dbt_ls_command_result(
    *, argv: tuple[str, ...], unique_ids: tuple[str, ...]
) -> DbtCommandResult:
    """Build a dbt ls command result with JSON-lines nodes."""

    stdout: str = "\n".join(json.dumps({"unique_id": unique_id}) for unique_id in unique_ids)
    return DbtCommandResult(argv=argv, returncode=0, stdout=stdout)


def build_sqlbuild_plan_output(model_names: tuple[str, ...]) -> PlanOutput:
    """Build a minimal SQLBuild plan output for dbt formatter tests."""

    return PlanOutput(
        model_entries=tuple(
            _build_sqlbuild_model_plan_entry(model_name) for model_name in model_names
        )
    )


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

    if "--select" not in argv:
        return ()
    values: list[str] = []
    index: int = argv.index("--select") + 1
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return tuple(values)


def extract_dbt_ls_excludes(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Extract exclude terms from a dbt ls argv for assertions."""

    if "--exclude" not in argv:
        return ()
    values: list[str] = []
    index: int = argv.index("--exclude") + 1
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return tuple(values)


def build_manifest_data(
    *, nodes: tuple[dict[str, object], ...], sources: tuple[dict[str, object], ...] = ()
) -> dict[str, object]:
    """Build a minimal dbt manifest payload for model lookup tests."""

    return {
        "nodes": {str(node["unique_id"]): node for node in nodes},
        "sources": {str(source["unique_id"]): source for source in sources},
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
    depends_on_nodes: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a minimal dbt manifest model node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "model",
        "package_name": package_name,
        "name": name,
    }
    if relation_name is not None:
        node["relation_name"] = relation_name
    if database is not None:
        node["database"] = database
    if schema is not None:
        node["schema"] = schema
    if alias is not None:
        node["alias"] = alias
    if checksum is not None:
        node["checksum"] = {"checksum": checksum}
    if fqn:
        node["fqn"] = list(fqn)
    if depends_on_nodes:
        node["depends_on"] = {"nodes": list(depends_on_nodes)}
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
    if relation_name is not None:
        node["relation_name"] = relation_name
    if database is not None:
        node["database"] = database
    if schema is not None:
        node["schema"] = schema
    if identifier is not None:
        node["identifier"] = identifier
    if loaded_at_field is not None:
        node["loaded_at_field"] = loaded_at_field
    if loaded_at_query is not None:
        node["loaded_at_query"] = loaded_at_query
    if freshness is not None:
        node["freshness"] = freshness
    if freshness_filter is not None:
        node["filter"] = freshness_filter
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
                    values={"tags": tags_by_model_name.get(model_name, ())}
                    if model_name in tags_by_model_name
                    else {}
                ),
                query_sql=sql,
                references=extract_sql_references(sql),
            )
        )
    return assemble_compiled_project(
        CompileProjectInputs(
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

    return {
        key.stable_id: tuple(dep.stable_id for dep in deps) for key, deps in graph_edges.items()
    }


def graph_key_stable_ids(keys: frozenset[DbtCombinedGraphKey]) -> tuple[str, ...]:
    """Render graph keys as sorted stable IDs for assertions."""

    return tuple(sorted(key.stable_id for key in keys))


def graph_key_from_stable_id(stable_id: str) -> DbtCombinedGraphKey:
    """Build a graph key from its stable string form."""

    owner, resource_type, name = stable_id.split(":", maxsplit=2)
    owner_enum: DbtCombinedGraphOwner = DbtCombinedGraphOwner(owner)
    resource_type_enum: DbtCombinedGraphResourceType = DbtCombinedGraphResourceType(resource_type)
    if (
        owner_enum == DbtCombinedGraphOwner.DBT
        and resource_type_enum == DbtCombinedGraphResourceType.SOURCE
    ):
        return dbt_source_graph_key(name)
    if owner_enum == DbtCombinedGraphOwner.DBT:
        return dbt_model_graph_key(name)
    return sqlbuild_model_graph_key(name)


def write_dbt_test_fingerprint(
    *, adapter: Any, connection: Any, unique_id: str, version_hash: str
) -> None:
    """Write one dbt fingerprint row for planning tests."""

    fingerprint: Fingerprint = Fingerprint(
        node_type=NODE_TYPE_DBT,
        node_name=unique_id,
        target_database=None,
        target_schema="main",
        target_name="orders",
        run_id="test",
        definition_hash=version_hash,
        version_hash=version_hash,
        schema_fingerprint=hashlib.sha256(b"").hexdigest(),
        definition="{}",
        metadata_json="{}",
        ts=datetime.now(tz=UTC),
    )
    write_fingerprint(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        fingerprint=fingerprint,
        render_qualified_name=adapter.render_qualified_name,
        render_framework_type=adapter.render_framework_type,
        render_create_table_sql=adapter.render_create_fingerprint_table_sql,
        render_create_index_sqls=adapter.render_create_fingerprint_index_sqls,
    )


def setup_dbt_model_planning_state(
    *,
    adapter: Any,
    connection: Any,
    unique_id: str,
    create_relation: bool,
    fingerprint_hash: str | None,
) -> None:
    """Create optional relation and fingerprint state for dbt model planning tests."""

    if create_relation:
        adapter.execute(connection, "CREATE TABLE main.orders AS SELECT 1 AS id")
    if fingerprint_hash is not None:
        write_dbt_test_fingerprint(
            adapter=adapter,
            connection=connection,
            unique_id=unique_id,
            version_hash=fingerprint_hash,
        )
