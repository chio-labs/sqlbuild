from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, QueryResult, RelationInfo, RowDiffResult
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.cli.commands.main.helpers.diff.output import has_diff_failures
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
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt.helpers.graph import (
    build_dbt_combined_graph,
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.lineage_selection import select_dbt_lineage_target
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner, build_dbt_ls_argv
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliConfigOverrides,
    DbtCliOptions,
    DbtColumnLineageTrace,
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtCommandResult,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLineageGraph,
    DbtLsNode,
    DbtModelPlanEntry,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.diff import (
    DbtDiffOptions,
    parse_dbt_diff_options,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtInteropCommand,
    DbtLineageDirection,
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReusePlanAction,
    DbtReusePlanReason,
)
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


def build_dbt_interop_plan_for_reuse_scope(
    *,
    dbt_selected_unique_ids: tuple[str, ...],
    dbt_required_unique_ids: tuple[str, ...] = (),
    dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]] | None = None,
) -> DbtInteropPlan:
    """Build a minimal interop plan for reuse scope tests."""

    return DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(),
        dbt_selected_unique_ids=dbt_selected_unique_ids,
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(
            dbt_required_unique_ids=dbt_required_unique_ids,
            dbt_anchor_unique_ids_by_term=dbt_anchor_unique_ids_by_term or {},
        ),
    )


def build_dbt_model_plan_entry(
    *,
    unique_id: str,
    action: DbtModelPlanAction,
    reason: DbtModelPlanReason,
    previous_metadata_json: str | None = None,
) -> DbtModelPlanEntry:
    """Build a minimal dbt model plan entry for reuse planning tests."""

    name: str = unique_id.rsplit(".", maxsplit=1)[-1]
    return DbtModelPlanEntry(
        unique_id=unique_id,
        package_name="analytics",
        name=name,
        action=action,
        reason=reason,
        relation_name=f"dev.{name}",
        previous_metadata_json=previous_metadata_json,
    )


def build_reuse_plan_current_manifest_nodes() -> tuple[dict[str, object], ...]:
    """Build current manifest nodes for reuse plan pipeline tests."""

    return (
        build_manifest_model_node(
            unique_id="model.analytics.orders",
            package_name="analytics",
            name="orders",
            relation_name="dev.orders",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.events",
            package_name="analytics",
            name="events",
            relation_name="dev.events",
            materialized="incremental",
            incremental_strategy="microbatch",
        ),
    )


def build_reuse_plan_reuse_manifest_nodes() -> tuple[dict[str, object], ...]:
    """Build reuse manifest nodes for reuse plan pipeline tests."""

    return (
        build_manifest_model_node(
            unique_id="model.analytics.orders",
            package_name="analytics",
            name="orders",
            relation_name="prod.orders",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.events",
            package_name="analytics",
            name="events",
            relation_name="prod.events",
            materialized="incremental",
            incremental_strategy="microbatch",
        ),
    )


def build_reuse_plan_origin_key_current_manifest_nodes() -> tuple[dict[str, object], ...]:
    """Build current manifest nodes for origin relation key tests."""

    return (
        build_manifest_model_node(
            unique_id="model.analytics.orders",
            package_name="analytics",
            name="orders",
            database="warehouse",
            schema="dev_marts",
            alias="orders_dev",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.customers",
            package_name="analytics",
            name="customers",
            database="warehouse",
            schema="dev_core",
            alias="customers_dev",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.payments",
            package_name="analytics",
            name="payments",
            database="lakehouse",
            schema="dev_marts",
            alias="payments_dev",
            materialized="table",
        ),
    )


def build_reuse_plan_origin_key_reuse_manifest_nodes() -> tuple[dict[str, object], ...]:
    """Build reuse manifest nodes for origin relation key tests."""

    return (
        build_manifest_model_node(
            unique_id="model.analytics.orders",
            package_name="analytics",
            name="orders",
            database="warehouse",
            schema="prod_marts",
            alias="orders_prod",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.customers",
            package_name="analytics",
            name="customers",
            database="warehouse",
            schema="prod_core",
            alias="customers_prod",
            materialized="table",
        ),
        build_manifest_model_node(
            unique_id="model.analytics.payments",
            package_name="analytics",
            name="payments",
            database="lakehouse",
            schema="prod_marts",
            alias="payments_prod",
            materialized="table",
        ),
    )


def assert_reuse_plan_output_matches(
    *,
    result: DbtReusePlanningResult | None,
    expected_is_none: bool,
    expected_complete_reuse_unique_ids: tuple[str, ...],
    expected_seeded_reuse_unique_ids: tuple[str, ...],
) -> None:
    """Assert reuse plan pipeline helper output matches expectations."""

    assert (result is None) is expected_is_none
    if result is None:
        return
    assert result.complete_reuse_unique_ids == expected_complete_reuse_unique_ids
    assert result.seeded_reuse_unique_ids == expected_seeded_reuse_unique_ids


def reuse_plan_rebuild_reasons(result: DbtReusePlanningResult) -> tuple[DbtReusePlanReason, ...]:
    """Return rebuild reasons from a dbt reuse planning result."""

    return tuple(
        entry.reason for entry in result.entries if entry.action == DbtReusePlanAction.REBUILD
    )


def build_reuse_execute_manifest() -> DbtManifestIndex:
    """Build a manifest for dbt complete reuse execution tests."""

    model: DbtManifestModel = DbtManifestModel(
        unique_id="model.analytics.fact_orders",
        package_name="analytics",
        name="fact_orders",
        relation_name="main.fact_orders",
        database=None,
        schema="main",
        alias="fact_orders",
        node_checksum="checksum-1",
        query_sql="select 1 as order_id, 111 as amount",
    )
    return DbtManifestIndex(
        models_by_unique_id={model.unique_id: model},
        models_by_name={model.name: (model,)},
        models_by_package_and_name={(model.package_name, model.name): model},
    )


def build_reuse_execute_plan() -> DbtInteropPlan:
    """Build a dbt interop plan with one complete reuse entry."""

    return build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(("sqb", "build", "--select", "downstream_orders"),),
        selection=DbtInteropSelectionResult(sqlbuild_model_names=("downstream_orders",)),
        dbt_reuse_plan=DbtReusePlanningResult(
            entries=(
                DbtReusePlanEntry(
                    unique_id="model.analytics.fact_orders",
                    action=DbtReusePlanAction.COMPLETE_REUSE,
                    reason=DbtReusePlanReason.DESTINATION_MISSING,
                    materialization="table",
                    destination_relation_name="main.fact_orders",
                    origin_relation_name="prod.fact_orders",
                ),
            )
        ),
    )


def build_fresh_schema_reuse_execute_manifest() -> DbtManifestIndex:
    """Build a manifest whose destination schema does not exist yet."""

    model: DbtManifestModel = DbtManifestModel(
        unique_id="model.analytics.fact_orders",
        package_name="analytics",
        name="fact_orders",
        relation_name='"dev_marts"."fact_orders"',
        database=None,
        schema="dev_marts",
        alias="fact_orders",
        node_checksum="checksum-1",
        query_sql="select 1 as order_id, 111 as amount",
    )
    return DbtManifestIndex(
        models_by_unique_id={model.unique_id: model},
        models_by_name={model.name: (model,)},
        models_by_package_and_name={(model.package_name, model.name): model},
    )


def build_fresh_schema_reuse_execute_plan() -> DbtInteropPlan:
    """Build a complete reuse plan whose destination uses a quoted fresh schema."""

    return build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_reuse_plan=DbtReusePlanningResult(
            entries=(
                DbtReusePlanEntry(
                    unique_id="model.analytics.fact_orders",
                    action=DbtReusePlanAction.COMPLETE_REUSE,
                    reason=DbtReusePlanReason.DESTINATION_MISSING,
                    materialization="table",
                    destination_relation_name='"dev_marts"."fact_orders"',
                    origin_relation_name='"marts"."fact_orders"',
                ),
            )
        ),
    )


def build_seeded_reuse_execute_plan(*, cursor_column: str | None) -> DbtInteropPlan:
    """Build a dbt interop plan with one seeded reuse entry."""

    return build_dbt_interop_plan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=(("sqb", "build", "--select", "downstream_events"),),
        selection=DbtInteropSelectionResult(sqlbuild_model_names=("downstream_events",)),
        dbt_reuse_plan=DbtReusePlanningResult(
            entries=(
                DbtReusePlanEntry(
                    unique_id="model.analytics.fact_orders",
                    action=DbtReusePlanAction.SEEDED_REUSE,
                    reason=DbtReusePlanReason.DESTINATION_MISSING,
                    materialization="incremental",
                    destination_relation_name="main.fact_orders",
                    origin_relation_name="prod.fact_orders",
                    cursor_column=cursor_column,
                ),
            )
        ),
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
    raw_code: str | None = None,
    compiled_code: str | None = None,
    depends_on_nodes: tuple[str, ...] = (),
    materialized: str | None = "view",
    incremental_strategy: str | None = None,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a minimal dbt manifest model node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "model",
        "package_name": package_name,
        "name": name,
        "raw_code": raw_code if raw_code is not None else f"select * from {name}",
    }
    if relation_name is not None:
        node["relation_name"] = relation_name
    if compiled_code is not None:
        node["compiled_code"] = compiled_code
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
    if materialized is not None:
        config: dict[str, object] = {"materialized": materialized}
        if incremental_strategy is not None:
            config["incremental_strategy"] = incremental_strategy
        if meta is not None:
            config["meta"] = meta
        node["config"] = config
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
    *,
    adapter: Any,
    connection: Any,
    unique_id: str,
    version_hash: str,
    definition: str = "select * from orders",
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
        definition=definition,
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


def build_lineage_manifest_data() -> dict[str, object]:
    """Build manifest data for mixed dbt/SQLBuild lineage unit tests."""

    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name="analytics.stg_orders",
                depends_on_nodes=("source.analytics.raw.orders",),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.int_orders",
                package_name="analytics",
                name="int_orders",
                relation_name="analytics.int_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        sources=(
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                relation_name="raw.orders",
            ),
        ),
    )


def build_column_lineage_manifest_data() -> dict[str, object]:
    """Build manifest data with compiled SQL for dbt column lineage unit tests."""

    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name='"db"."raw"."stg_orders"',
                compiled_code='select order_id, amount from "db"."raw"."orders"',
                depends_on_nodes=("source.analytics.raw.orders",),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name='"db"."marts"."fact_orders"',
                compiled_code='select order_id, amount from "db"."raw"."stg_orders"',
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        sources=(
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                relation_name='"db"."raw"."orders"',
            ),
        ),
    )


def build_column_lineage_star_manifest_data(*, include_source_schema: bool) -> dict[str, object]:
    """Build manifest data for SELECT * dbt column lineage tests."""

    source: dict[str, object] = build_manifest_source_node(
        unique_id="source.analytics.raw.orders",
        relation_name='"db"."raw"."orders"',
    )
    if include_source_schema:
        source["columns"] = {
            "order_id": {"name": "order_id", "data_type": "INTEGER"},
            "amount": {"name": "amount", "data_type": "INTEGER"},
        }
    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name="raw.stg_orders",
                compiled_code="select * from raw.orders",
                depends_on_nodes=("source.analytics.raw.orders",),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name="marts.fact_orders",
                compiled_code="select * from raw.stg_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        sources=(source,),
    )


def build_column_lineage_join_manifest_data() -> dict[str, object]:
    """Build manifest data with aliases, joins, and expression transforms."""

    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name="raw.stg_orders",
                compiled_code="select o.order_id, o.amount from raw.orders as o",
                depends_on_nodes=("source.analytics.raw.orders",),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name="fact_orders",
                compiled_code=(
                    "select o.order_id, o.amount * 100 as amount_cents "
                    "from raw.stg_orders o join raw.customers c on o.order_id = c.order_id"
                ),
                depends_on_nodes=(
                    "model.analytics.stg_orders",
                    "source.analytics.raw.customers",
                ),
            ),
        ),
        sources=(
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                relation_name="raw.orders",
            ),
            build_manifest_source_node(
                unique_id="source.analytics.raw.customers",
                name="customers",
                relation_name="raw.customers",
            ),
        ),
    )


def build_column_lineage_quoted_schema_manifest_data() -> dict[str, object]:
    """Build manifest data with quoted schema-qualified compiled SQL relations."""

    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name='"raw"."stg_orders"',
                compiled_code='select order_id, amount from "raw"."orders"',
                depends_on_nodes=("source.analytics.raw.orders",),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name='"marts"."fact_orders"',
                compiled_code='select order_id, amount from "raw"."stg_orders"',
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        sources=(
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                relation_name='"db"."raw"."orders"',
            ),
        ),
    )


def build_column_lineage_ambiguous_table_manifest_data() -> dict[str, object]:
    """Build manifest data where table-only relation names are ambiguous."""

    return build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name='"marts"."fact_orders"',
                compiled_code="select order_id, amount from orders",
                depends_on_nodes=(
                    "source.analytics.raw.orders",
                    "source.analytics.archive.orders",
                ),
            ),
        ),
        sources=(
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                relation_name='"db"."raw"."orders"',
            ),
            build_manifest_source_node(
                unique_id="source.analytics.archive.orders",
                name="orders",
                relation_name='"db"."archive"."orders"',
            ),
        ),
    )


def column_lineage_edge_ids(edge: ColumnLineageEdge) -> tuple[str, str]:
    """Return compact source/target identifiers for column lineage assertions."""

    source: QualifiedLineageColumn = edge.source
    target: QualifiedLineageColumn = edge.target
    return (_lineage_column_id(source), _lineage_column_id(target))


def column_lineage_target_id(trace: DbtColumnLineageTrace) -> tuple[str, str, str]:
    """Return compact target identity for dbt column lineage assertions."""

    return (
        str(trace.target.resource_type),
        trace.target.resource_name,
        trace.target.column_name,
    )


class FakeLineageSourceSchemaAdapter(BaseAdapter):
    """Adapter stub for dbt source schema inspection unit tests."""

    adapter_name: ClassVar[str] = "fake_lineage_source_schema"

    def __init__(self, columns_by_relation: dict[str, tuple[ColumnInfo, ...]]) -> None:
        self.columns_by_relation: dict[str, tuple[ColumnInfo, ...]] = columns_by_relation
        self.described_relations: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        return object()

    def execute(self, connection: object, sql: str) -> object:
        raise AssertionError("execute should not be called in source schema tests")

    def query(self, connection: object, sql: str, *, limit: int | None) -> QueryResult:
        raise AssertionError("query should not be called in source schema tests")

    def close(self, connection: object) -> None:
        return None

    def describe_relation(self, connection: object, relation: str) -> tuple[ColumnInfo, ...]:
        self.described_relations.append(relation)
        columns: tuple[ColumnInfo, ...] | None = self.columns_by_relation.get(relation)
        if columns is None:
            raise RuntimeError(f"missing relation {relation}")
        return columns


class FakeReusePlanAdapter(BaseAdapter):
    """Adapter stub for dbt reuse origin relation listing tests."""

    adapter_name: ClassVar[str] = "fake_reuse_plan"

    def __init__(self, relations: tuple[RelationInfo, ...]) -> None:
        self.relations: tuple[RelationInfo, ...] = relations
        self.list_relation_calls: list[
            tuple[str | None, tuple[str, ...] | None, tuple[str, ...] | None]
        ] = []

    def connect(self, config: dict[str, object]) -> object:
        return object()

    def execute(self, connection: object, sql: str) -> object:
        raise AssertionError("execute should not be called in reuse plan tests")

    def close(self, connection: object) -> None:
        return None

    def list_relations(
        self,
        connection: object,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection
        self.list_relation_calls.append((database, schemas, names))
        return tuple(
            relation
            for relation in self.relations
            if relation.database == database
            and (schemas is None or relation.schema in schemas)
            and (names is None or relation.name in names)
        )


def _lineage_column_id(column: QualifiedLineageColumn) -> str:
    resource_name: str = column.resource_name
    column_name: str = column.column_name
    return f"{resource_name}:{column_name}"


def build_lineage_graph_for_output_test() -> DbtLineageGraph:
    """Build a mixed lineage graph for output formatter tests."""

    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=build_lineage_manifest_data())
    project: CompiledProject = build_compiled_project_with_models(
        {"fact_orders": 'select * from __dbt_ref("int_orders")'}
    )
    combined_graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    return select_dbt_lineage_target(
        project=project,
        manifest=manifest,
        graph=combined_graph,
        target="fact_orders",
        direction=DbtLineageDirection.UPSTREAM,
        depth=None,
    )


def build_depth_zero_lineage_graph_for_output_test() -> DbtLineageGraph:
    """Build a single-node mixed lineage graph for output formatter tests."""

    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=build_lineage_manifest_data())
    project: CompiledProject = build_compiled_project_with_models(
        {
            "fact_orders": 'select * from __dbt_ref("int_orders")',
            "mart_orders": 'select * from __ref("fact_orders")',
        }
    )
    combined_graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    return select_dbt_lineage_target(
        project=project,
        manifest=manifest,
        graph=combined_graph,
        target="mart_orders",
        direction=DbtLineageDirection.UPSTREAM,
        depth=0,
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


def build_dbt_diff_manifest_model_node(
    *,
    unique_id: str,
    name: str,
    schema: str,
    relation_name: str,
    unique_key: object | None = None,
    node_meta: dict[str, object] | None = None,
    config_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a dbt manifest model node with diff-relevant config and meta."""

    config: dict[str, object] = {"materialized": "table"}
    if unique_key is not None:
        config["unique_key"] = unique_key
    if config_meta is not None:
        config["meta"] = config_meta
    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "model",
        "package_name": "analytics",
        "name": name,
        "schema": schema,
        "alias": name,
        "relation_name": relation_name,
        "raw_code": f"select * from {name}",
        "config": config,
    }
    if node_meta is not None:
        node["meta"] = node_meta
    return node


def build_dbt_diff_manifest_index(
    *,
    schema: str,
    relation_name: str,
    config: dict[str, object],
    unique_id: str = "model.analytics.dbt_orders",
    name: str = "dbt_orders",
    node_meta: dict[str, object] | None = None,
    config_meta: dict[str, object] | None = None,
) -> DbtManifestIndex:
    """Build a single-model dbt manifest index for diff executor tests."""

    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_dbt_diff_manifest_model_node(
                    unique_id=unique_id,
                    name=name,
                    schema=schema,
                    relation_name=relation_name,
                    unique_key=config.get("unique_key"),
                    node_meta=node_meta,
                    config_meta=config_meta,
                ),
            )
        )
    )


def build_dbt_diff_ls_node(
    *,
    unique_id: str = "model.analytics.dbt_orders",
    name: str = "dbt_orders",
    resource_type: str = "model",
) -> DbtLsNode:
    """Build a dbt ls node for diff executor tests."""

    return DbtLsNode(
        unique_id=unique_id,
        resource_type=resource_type,
        package_name="analytics",
        name=name,
        fqn=("analytics", name),
    )


def create_dbt_diff_relation(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    name: str,
    rows: tuple[tuple[object, ...], ...],
) -> None:
    """Create a dbt diff order table from literal rows in a real DuckDB schema."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    union_sql: str = " UNION ALL ".join(
        f"SELECT {order_id} AS order_id, {amount} AS amount_cents" for order_id, amount in rows
    )
    adapter.execute(connection, f"CREATE TABLE {schema}.{name} AS {union_sql}")


def build_dbt_diff_schema_only_options() -> DbtDiffOptions:
    """Build parsed schema-only dbt diff options for executor tests."""

    return parse_dbt_diff_options(("--select", "dbt_orders", "--schema-only"))


def build_dbt_diff_full_options() -> DbtDiffOptions:
    """Build parsed full dbt diff options for executor tests."""

    return parse_dbt_diff_options(("--select", "dbt_orders", "--full"))


def build_dbt_diff_bounded_options(bounded: str) -> DbtDiffOptions:
    """Build parsed bounded dbt diff options for executor tests."""

    return parse_dbt_diff_options(("--select", "dbt_orders", "--bounded", bounded))


def assert_dbt_diff_execution_result(
    *,
    result: DiffExecutionResult,
    expected_model_names: tuple[str, ...],
    expected_has_row_result: bool,
    expected_unequal_count: int,
    expected_left_only_count: int,
    expected_right_only_count: int,
    expected_has_failures: bool,
) -> None:
    """Assert dbt diff execution result shape, row counts, and failure flag."""

    assert tuple(item.name for item in result.model_results) == expected_model_names
    row_result: RowDiffResult | None = (
        result.model_results[0].row_result if result.model_results else None
    )
    assert (row_result is not None) == expected_has_row_result
    unequal: int = row_result.unequal_count if row_result is not None else 0
    left_only: int = row_result.left_only_count if row_result is not None else 0
    right_only: int = row_result.right_only_count if row_result is not None else 0
    assert unequal == expected_unequal_count
    assert left_only == expected_left_only_count
    assert right_only == expected_right_only_count
    assert has_diff_failures(result) == expected_has_failures


def create_dbt_diff_unique_key_relation(
    *, adapter: DuckDbAdapter, connection: object, schema: str, amount_cents: int
) -> None:
    """Create a two-column-key dbt diff relation for unique key tests."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    adapter.execute(
        connection,
        f"CREATE TABLE {schema}.dbt_orders AS "
        f"SELECT 1 AS order_id, 1 AS line_id, {amount_cents} AS amount_cents",
    )


def create_dbt_diff_relation_with_columns(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    column_sql: str,
) -> None:
    """Create a dbt diff relation from an explicit column projection."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    adapter.execute(connection, f"CREATE TABLE {schema}.dbt_orders AS SELECT {column_sql}")


def create_dbt_diff_cursor_relation(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    cursor_column: str,
    cursor_kind: str,
) -> None:
    """Create a dbt diff relation that carries a bounded cursor column."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    cursor_value: str = (
        "cast('2026-06-17 00:00:00' as timestamp)" if cursor_kind == "timestamp" else "10"
    )
    adapter.execute(
        connection,
        f"CREATE TABLE {schema}.dbt_orders AS "
        f"SELECT 1 AS order_id, 100 AS amount_cents, {cursor_value} AS {cursor_column}",
    )


def create_dbt_diff_relation_when_requested(
    *, adapter: DuckDbAdapter, connection: object, schema: str, create: bool
) -> None:
    """Create a dbt diff relation only when requested, else just the schema."""

    if not create:
        adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
        return
    create_dbt_diff_relation(
        adapter=adapter,
        connection=connection,
        schema=schema,
        name="dbt_orders",
        rows=((1, 1),),
    )
