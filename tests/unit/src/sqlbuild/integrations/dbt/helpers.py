from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
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
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledModelSqlTestPayload,
    CompiledSqlTest,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
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
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.executor.diff.models import DiffExecutionResult
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner, build_dbt_ls_argv
from sqlbuild.integrations.dbt.helpers.graph.core import (
    build_dbt_combined_graph,
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.helpers.lineage.selection import select_dbt_lineage_target
from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.planning.plan import build_dbt_interop_plan
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
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


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

    def __init__(self) -> None:
        self.compile_full_refresh_values: list[bool] = []

    def compile(self, *, options: DbtCliOptions, full_refresh: bool = False) -> DbtCommandResult:
        del options
        self.compile_full_refresh_values.append(full_refresh)
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


def build_project_with_expected_sql_test_targets(
    *,
    expected_model_names: tuple[str, ...],
    sqlbuild_model_names: tuple[str, ...] = (),
    mock_model_names: tuple[str, ...] = (),
) -> CompiledProject:
    """Build a minimal project with one model-mode SQL test."""

    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=0,
        header_values={},
        sql_body="select 1",
        name="test_dbt_fact_orders",
    )
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("/repo/tests/unit/test_dbt_fact_orders.sql"),
        relative_path=Path("tests/unit/test_dbt_fact_orders.sql"),
        contents="TEST();",
        blocks=(test_block,),
    )
    sql_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="test_dbt_fact_orders",
        ),
        scope_deps=(),
        name="test_dbt_fact_orders",
        test_file=test_file,
        test_block=test_block,
        sql_body="TEST();",
        payload=CompiledModelSqlTestPayload(
            expected_model_names=expected_model_names,
            mock_dbt_ref_names=mock_model_names,
        ),
    )
    models: tuple[CompiledModel, ...] = tuple(
        CompiledModel(
            key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
            deps=(),
            name=model_name,
            relative_path=Path(f"models/{model_name}.sql"),
            query_sql="select 1",
            config=CompileModelConfig(),
            destination=CompiledRelationLocation(
                database=None,
                schema=None,
                name=model_name,
                qualified_name=model_name,
            ),
        )
        for model_name in sqlbuild_model_names
    )
    return CompiledProject(
        run_id="run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=models,
        sql_tests=(sql_test,),
    )


def build_project_with_multiple_dbt_sql_test_boundaries() -> CompiledProject:
    """Build two dbt-targeting SQL tests with different mock boundaries."""

    test_specs: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("test_dbt_fact_orders_chain", ()),
        ("test_dbt_fact_orders_boundary", ("analytics__stg_orders",)),
    )
    sql_tests: list[CompiledSqlTest] = []
    test_name: str
    mock_model_names: tuple[str, ...]
    for index, (test_name, mock_model_names) in enumerate(test_specs):
        test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
            test_index=index,
            header_values={},
            sql_body="select 1",
            name=test_name,
        )
        test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
            file_path=Path(f"/repo/tests/unit/{test_name}.sql"),
            relative_path=Path(f"tests/unit/{test_name}.sql"),
            contents="TEST();",
            blocks=(test_block,),
        )
        sql_tests.append(
            CompiledSqlTest(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SQL_TEST,
                    name=test_name,
                ),
                scope_deps=(),
                name=test_name,
                test_file=test_file,
                test_block=test_block,
                sql_body="TEST();",
                payload=CompiledModelSqlTestPayload(
                    expected_model_names=("fact_orders",),
                    mock_dbt_ref_names=mock_model_names,
                ),
            )
        )
    return CompiledProject(
        run_id="run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        sql_tests=tuple(sql_tests),
    )


def build_dbt_sql_test_target_manifest(
    *,
    dep_relation_name: str = '"analytics"."stg_orders"',
    fact_compiled_code: str
    | None = 'select * from "analytics"."stg_orders" where amount_cents > 0',
    include_ambiguous_package: bool = False,
) -> DbtManifestIndex:
    """Build a manifest fixture for dbt SQL test target adaptation."""

    fact_node: dict[str, object] = build_manifest_model_node(
        unique_id="model.analytics.fact_orders",
        package_name="analytics",
        name="fact_orders",
        relation_name='"analytics"."fact_orders"',
        raw_code="select * from {{ ref('stg_orders') }}",
        compiled_code=fact_compiled_code,
        depends_on_nodes=("model.analytics.stg_orders",),
    )
    if fact_compiled_code is None:
        fact_node.pop("compiled_code", None)
    nodes: tuple[dict[str, object], ...] = (
        build_manifest_model_node(
            unique_id="model.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name=dep_relation_name,
            compiled_code="select * from raw.orders",
        ),
        fact_node,
    )
    if include_ambiguous_package:
        nodes = (
            *nodes,
            build_manifest_model_node(
                unique_id="model.finance.fact_orders",
                package_name="finance",
                name="fact_orders",
                relation_name='"finance"."fact_orders"',
                compiled_code="select 1 as order_id",
            ),
        )
    return build_dbt_manifest_index(raw_data=build_manifest_data(nodes=nodes))


def build_dbt_sql_test_target_success_manifest(*, manifest_kind: str) -> DbtManifestIndex:
    """Build a success manifest variant for dbt SQL test target tests."""

    if manifest_kind == "source_dependency":
        return build_dbt_sql_test_source_seed_manifest(dependency_kind="source")
    if manifest_kind == "source_unquoted":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="source",
            relation_name="raw.orders",
            compiled_code="select * from raw.orders",
        )
    if manifest_kind == "source_three_part":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="source",
            relation_name='"warehouse"."raw"."orders"',
            compiled_code='select * from "warehouse"."raw"."orders"',
        )
    if manifest_kind == "source_alias":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="source",
            relation_name='"raw"."orders_alias"',
            compiled_code='select * from "raw"."orders_alias"',
        )
    if manifest_kind == "source_ambiguous_fixture":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="source",
            include_ambiguous_package=True,
        )
    if manifest_kind == "chain_source_dependency":
        return build_dbt_sql_test_model_chain_manifest(dependency_kind="source")
    if manifest_kind == "seed_dependency":
        return build_dbt_sql_test_source_seed_manifest(dependency_kind="seed")
    if manifest_kind == "seed_unquoted":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="seed",
            relation_name="analytics.countries",
            compiled_code="select * from analytics.countries",
        )
    if manifest_kind == "seed_three_part":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="seed",
            relation_name='"warehouse"."analytics"."countries"',
            compiled_code='select * from "warehouse"."analytics"."countries"',
        )
    if manifest_kind == "seed_alias":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="seed",
            relation_name='"analytics"."countries_alias"',
            compiled_code='select * from "analytics"."countries_alias"',
        )
    if manifest_kind == "seed_ambiguous_fixture":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="seed",
            include_ambiguous_package=True,
        )
    if manifest_kind == "chain_seed_dependency":
        return build_dbt_sql_test_model_chain_manifest(dependency_kind="seed")
    if manifest_kind == "chain_snapshot_boundary":
        return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="snapshot")
    if manifest_kind == "chain_ephemeral_boundary":
        return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="ephemeral")
    if manifest_kind == "unquoted":
        return build_dbt_sql_test_target_manifest(
            dep_relation_name="analytics.stg_orders",
            fact_compiled_code="select * from analytics.stg_orders where amount_cents > 0",
        )
    if manifest_kind == "three_part":
        return build_dbt_sql_test_target_manifest(
            dep_relation_name='"warehouse"."analytics"."stg_orders"',
            fact_compiled_code=(
                'select * from "warehouse"."analytics"."stg_orders" where amount_cents > 0'
            ),
        )
    if manifest_kind == "alias":
        return build_dbt_sql_test_target_manifest(
            dep_relation_name='"analytics"."stg_orders_alias"',
            fact_compiled_code='select * from "analytics"."stg_orders_alias"',
        )
    if manifest_kind == "ambiguous":
        return build_dbt_sql_test_target_manifest(include_ambiguous_package=True)
    if manifest_kind == "relation_in_string_and_comment":
        return build_dbt_sql_test_target_manifest(
            dep_relation_name="analytics.stg_orders",
            fact_compiled_code=(
                "-- upstream analytics.stg_orders\n"
                "select *, 'analytics.stg_orders' as src "
                "from analytics.stg_orders where amount_cents > 0"
            ),
        )
    return build_dbt_sql_test_target_manifest()


def build_dbt_sql_test_target_error_manifest(*, manifest_kind: str) -> DbtManifestIndex:
    """Build an error manifest variant for dbt SQL test target tests."""

    if manifest_kind in {"source_dependency", "source_ambiguous_fixture"}:
        return build_dbt_sql_test_source_seed_manifest(dependency_kind="source")
    if manifest_kind == "source_unresolved_relation":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="source",
            compiled_code="select * from raw.unexpected_orders",
        )
    if manifest_kind == "chain_missing_compiled_sql":
        return build_dbt_sql_test_model_chain_manifest(
            dependency_kind="source",
            upstream_compiled_code=None,
        )
    if manifest_kind == "chain_unresolved_relation":
        return build_dbt_sql_test_model_chain_manifest(
            dependency_kind="source",
            upstream_compiled_code="select * from raw.unexpected_orders",
        )
    if manifest_kind == "chain_snapshot_boundary":
        return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="snapshot")
    if manifest_kind == "chain_ephemeral_boundary":
        return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="ephemeral")
    if manifest_kind in {"seed_dependency", "seed_ambiguous_fixture"}:
        return build_dbt_sql_test_source_seed_manifest(dependency_kind="seed")
    if manifest_kind == "seed_unresolved_relation":
        return build_dbt_sql_test_source_seed_manifest(
            dependency_kind="seed",
            compiled_code="select * from analytics.unexpected_countries",
        )
    if manifest_kind == "ambiguous":
        return build_dbt_sql_test_target_manifest(include_ambiguous_package=True)
    if manifest_kind == "missing_compiled_sql":
        return build_dbt_sql_test_target_manifest(fact_compiled_code=None)
    return build_dbt_sql_test_target_manifest(
        fact_compiled_code="select * from analytics.unexpected_orders"
    )


def build_dbt_sql_test_source_seed_manifest(
    *,
    dependency_kind: str,
    relation_name: str | None = None,
    compiled_code: str | None = None,
    include_ambiguous_package: bool = False,
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a source or seed dependency."""

    dependency_unique_id: str = (
        "source.analytics.raw.orders" if dependency_kind == "source" else "seed.analytics.countries"
    )
    default_relation_name: str = (
        '"raw"."orders"' if dependency_kind == "source" else '"analytics"."countries"'
    )
    default_compiled_code: str = (
        'select * from "raw"."orders"'
        if dependency_kind == "source"
        else 'select * from "analytics"."countries"'
    )
    source_nodes: tuple[dict[str, object], ...] = (
        (
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                package_name="analytics",
                source_name="raw",
                name="orders",
                relation_name=relation_name or default_relation_name,
            ),
        )
        if dependency_kind == "source"
        else ()
    )
    if dependency_kind == "source" and include_ambiguous_package:
        source_nodes = (
            *source_nodes,
            build_manifest_source_node(
                unique_id="source.finance.raw.orders",
                package_name="finance",
                source_name="raw",
                name="orders",
                relation_name='"finance_raw"."orders"',
            ),
        )
    seed_nodes: tuple[dict[str, object], ...] = (
        (
            build_manifest_seed_node(
                unique_id="seed.analytics.countries",
                package_name="analytics",
                name="countries",
                relation_name=relation_name or default_relation_name,
            ),
        )
        if dependency_kind == "seed"
        else ()
    )
    if dependency_kind == "seed" and include_ambiguous_package:
        seed_nodes = (
            *seed_nodes,
            build_manifest_seed_node(
                unique_id="seed.finance.countries",
                package_name="finance",
                name="countries",
                relation_name='"finance"."countries"',
            ),
        )
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    relation_name='"analytics"."fact_orders"',
                    compiled_code=compiled_code or default_compiled_code,
                    depends_on_nodes=(dependency_unique_id,),
                ),
                *seed_nodes,
            ),
            sources=source_nodes,
        )
    )


def build_dbt_sql_test_model_chain_manifest(
    *, dependency_kind: str, upstream_compiled_code: str | None | object = "default"
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a dbt model chain."""

    source_nodes: tuple[dict[str, object], ...] = (
        (
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                package_name="analytics",
                source_name="raw",
                name="orders",
                relation_name='"raw"."orders"',
            ),
        )
        if dependency_kind == "source"
        else ()
    )
    seed_nodes: tuple[dict[str, object], ...] = (
        (
            build_manifest_seed_node(
                unique_id="seed.analytics.countries",
                package_name="analytics",
                name="countries",
                relation_name='"analytics"."countries"',
            ),
        )
        if dependency_kind == "seed"
        else ()
    )
    upstream_dependency_unique_id: str = (
        "source.analytics.raw.orders" if dependency_kind == "source" else "seed.analytics.countries"
    )
    compiled_code: str | None = (
        (
            'select order_id from "raw"."orders"'
            if dependency_kind == "source"
            else 'select country_code from "analytics"."countries"'
        )
        if upstream_compiled_code == "default"
        else cast(str | None, upstream_compiled_code)
    )
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.stg_orders",
                    package_name="analytics",
                    name="stg_orders",
                    relation_name='"analytics"."stg_orders"',
                    compiled_code=compiled_code,
                    depends_on_nodes=(upstream_dependency_unique_id,),
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    relation_name='"analytics"."fact_orders"',
                    compiled_code='select order_id from "analytics"."stg_orders"',
                    depends_on_nodes=("model.analytics.stg_orders",),
                ),
                *seed_nodes,
            ),
            sources=source_nodes,
        )
    )


def build_dbt_sql_test_boundary_chain_manifest(*, boundary_kind: str) -> DbtManifestIndex:
    """Build a dbt chain manifest whose intermediate node is a snapshot or ephemeral."""

    intermediate_node: dict[str, object] = (
        build_manifest_model_node(
            unique_id="model.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name='"analytics"."stg_orders"',
            compiled_code='select order_id from "raw"."orders"',
            materialized="ephemeral",
            depends_on_nodes=("source.analytics.raw.orders",),
        )
        if boundary_kind == "ephemeral"
        else build_manifest_model_node(
            unique_id="snapshot.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name='"analytics"."stg_orders"',
            compiled_code='select order_id from "raw"."orders"',
            resource_type="snapshot",
            materialized="table",
            depends_on_nodes=("source.analytics.raw.orders",),
        )
    )
    intermediate_unique_id: str = str(intermediate_node["unique_id"])
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                intermediate_node,
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    relation_name='"analytics"."fact_orders"',
                    compiled_code='select order_id from "analytics"."stg_orders"',
                    depends_on_nodes=(intermediate_unique_id,),
                ),
            ),
            sources=(
                build_manifest_source_node(
                    unique_id="source.analytics.raw.orders",
                    package_name="analytics",
                    source_name="raw",
                    name="orders",
                    relation_name='"raw"."orders"',
                ),
            ),
        )
    )


def build_project_with_source_relation_collision() -> CompiledProject:
    """Build a minimal project whose SQLBuild source matches the dbt source relation."""

    source_entry: SourceEntry = SourceEntry(name="raw__orders", schema="raw", table="orders")
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("/repo/sources/raw.yml"),
        relative_path=Path("sources/raw.yml"),
        contents="",
        source_entries=(source_entry,),
    )
    return replace(
        build_project_with_expected_sql_test_targets(expected_model_names=("fact_orders",)),
        sources=(
            CompiledSource(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SOURCE, name="raw__orders"
                ),
                deps=(),
                name="raw__orders",
                source_entry=source_entry,
                source_file=source_file,
            ),
        ),
    )


def build_project_with_seed_relation_collision(
    *, qualified_name: str | None = '"analytics"."countries"'
) -> CompiledProject:
    """Build a minimal project whose SQLBuild seed matches the dbt seed relation."""

    seed_file: DiscoveredSeedFile = DiscoveredSeedFile(
        file_path=Path("/repo/seeds/countries.csv"),
        relative_path=Path("seeds/countries.csv"),
    )
    schema_file: DiscoveredSchemaFile = DiscoveredSchemaFile(
        file_path=Path("/repo/seeds/schema.yml"),
        relative_path=Path("seeds/schema.yml"),
        contents="",
        model_entries=(),
        seed_entries=(SchemaSeedEntry(name="countries"),),
    )
    return replace(
        build_project_with_expected_sql_test_targets(expected_model_names=("fact_orders",)),
        seeds=(
            CompiledSeed(
                key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name="countries"),
                deps=(),
                name="countries",
                seed_file=seed_file,
                schema_entry=SchemaSeedEntry(name="countries"),
                schema_file=schema_file,
                destination=CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="countries",
                    qualified_name=qualified_name,
                ),
            ),
        ),
    )


def build_dbt_sql_test_target_error_project(*, project_kind: str) -> CompiledProject:
    """Build an error project variant for dbt SQL test target tests."""

    if project_kind == "model_name_collision":
        return build_project_with_expected_sql_test_targets(
            expected_model_names=("fact_orders",),
            sqlbuild_model_names=("fact_orders",),
        )
    if project_kind == "source_relation_collision":
        return build_project_with_source_relation_collision()
    if project_kind == "seed_relation_collision":
        return build_project_with_seed_relation_collision()
    if project_kind == "seed_relation_collision_unqualified":
        return build_project_with_seed_relation_collision(qualified_name=None)
    return build_project_with_expected_sql_test_targets(expected_model_names=("fact_orders",))


def resolve_dbt_sql_test_fixture_names(
    *,
    manifest: DbtManifestIndex,
    fixture_kind: str,
    known_names: set[str],
) -> set[str]:
    """Resolve dbt-backed SQL test fixture names for a source or seed."""

    resolver: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=manifest)
    if fixture_kind == "model":
        return resolver.extend_sql_test_model_names(known_model_names=known_names)
    if fixture_kind == "source":
        return resolver.extend_sql_test_source_names(known_source_names=known_names)
    return resolver.extend_sql_test_seed_names(known_seed_names=known_names)


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

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": resource_type,
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
    if depends_on_nodes or depends_on_macro_ids:
        node["depends_on"] = {
            "nodes": list(depends_on_nodes),
            "macros": list(depends_on_macro_ids),
        }
    if materialized is not None:
        config: dict[str, object] = {"materialized": materialized}
        if incremental_strategy is not None:
            config["incremental_strategy"] = incremental_strategy
        if meta is not None:
            config["meta"] = meta
        if config_overrides is not None:
            config.update(config_overrides)
        node["config"] = config
    return node


def build_manifest_macro_node(
    *, unique_id: str, macro_sql: str, depends_on_macro_ids: tuple[str, ...] = ()
) -> dict[str, object]:
    """Build a minimal dbt manifest macro node."""

    return {
        "unique_id": unique_id,
        "resource_type": "macro",
        "macro_sql": macro_sql,
        "depends_on": {"macros": list(depends_on_macro_ids)},
    }


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


def build_dbt_selection_staleness_manifest(
    *,
    model_unique_ids: tuple[str, ...],
    seed_unique_ids: tuple[str, ...],
    source_unique_ids: tuple[str, ...],
) -> DbtManifestIndex:
    """Build a minimal manifest for dbt selection staleness adapter tests."""

    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                *(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name=unique_id.rsplit(".", 1)[-1],
                        relation_name=unique_id.rsplit(".", 1)[-1],
                        checksum="same_hash",
                    )
                    for unique_id in model_unique_ids
                ),
                *(
                    build_manifest_seed_node(
                        unique_id=unique_id,
                        name=unique_id.rsplit(".", 1)[-1],
                    )
                    for unique_id in seed_unique_ids
                ),
            ),
            sources=tuple(
                build_manifest_source_node(
                    unique_id=unique_id,
                    source_name=unique_id.split(".")[-2],
                    name=unique_id.rsplit(".", 1)[-1],
                )
                for unique_id in source_unique_ids
            ),
        )
    )


def build_dbt_selection_staleness_graph(
    *, upstream_deps: dict[str, tuple[str, ...]]
) -> DbtCombinedGraph:
    """Build a combined dbt graph from unique-id upstream dependencies."""

    mapped_upstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]] = {
        build_dbt_selection_staleness_key(unique_id): tuple(
            build_dbt_selection_staleness_key(upstream_unique_id)
            for upstream_unique_id in upstream_unique_ids
        )
        for unique_id, upstream_unique_ids in upstream_deps.items()
    }
    nodes: frozenset[DbtCombinedGraphKey] = frozenset(
        key for item in mapped_upstream_deps.items() for key in (item[0], *item[1])
    )
    return DbtCombinedGraph(nodes=nodes, upstream_deps=mapped_upstream_deps, downstream_deps={})


def build_dbt_selection_staleness_key(unique_id: str) -> DbtCombinedGraphKey:
    """Build the combined graph key shape used by dbt model planning."""

    resource_type: DbtCombinedGraphResourceType = DbtCombinedGraphResourceType.MODEL
    if unique_id.startswith(("seed.", "source.")):
        resource_type = DbtCombinedGraphResourceType.SOURCE
    return DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=resource_type,
        name=unique_id,
    )


def build_dbt_selection_staleness_entry(
    *, unique_id: str, action: DbtModelPlanAction, reason: DbtModelPlanReason
) -> DbtModelPlanEntry:
    """Build a dbt model plan entry for staleness warning tests."""

    name: str = unique_id.rsplit(".", 1)[-1]
    return DbtModelPlanEntry(
        unique_id=unique_id,
        package_name="analytics",
        name=name,
        action=action,
        reason=reason,
        relation_name=name,
    )


def build_manifest_seed_node(
    *,
    unique_id: str,
    package_name: str = "analytics",
    name: str = "countries",
    relation_name: str | None = None,
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
    if relation_name is not None:
        node["relation_name"] = relation_name
    if checksum is not None:
        node["checksum"] = {"checksum": checksum}
    if config_overrides is not None:
        node["config"] = config_overrides
    if root_path is not None:
        node["root_path"] = root_path
    if original_file_path is not None:
        node["original_file_path"] = original_file_path
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


def build_dbt_clone_manifest_index(
    *,
    schema: str,
    relation_name: str,
    materialized: str,
    compiled_code: str | None = None,
    unique_id: str = "model.analytics.dbt_orders",
    name: str = "dbt_orders",
) -> DbtManifestIndex:
    """Build a single-model dbt manifest index for clone executor tests."""

    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name=name,
                    relation_name=relation_name,
                    schema=schema,
                    alias=name,
                    materialized=materialized,
                    raw_code=(
                        "{{ config(materialized='view') }}\nSELECT 99 AS order_id, 'raw' AS status"
                    ),
                    compiled_code=compiled_code,
                ),
            )
        )
    )


def build_dbt_clone_reuse_manifest_index(
    *, include_model: bool, materialized: str
) -> DbtManifestIndex:
    """Build a reuse manifest index for clone executor tests."""

    if not include_model:
        return build_dbt_manifest_index(raw_data=build_manifest_data(nodes=()))
    return build_dbt_clone_manifest_index(
        schema="prod",
        relation_name="prod.dbt_orders",
        materialized=materialized,
    )


def create_dbt_clone_relation(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    name: str = "dbt_orders",
    rows: tuple[tuple[object, ...], ...] = ((1, "origin"),),
) -> None:
    """Create a dbt clone table from literal rows in a real DuckDB schema."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    selects: list[str] = []
    row: tuple[object, ...]
    for row in rows:
        order_id: int = cast(int, row[0])
        status: str = cast(str, row[1])
        selects.append(f"SELECT {order_id} AS order_id, '{status}' AS status")
    union_sql: str = " UNION ALL ".join(selects)
    adapter.execute(connection, f"CREATE OR REPLACE TABLE {schema}.{name} AS {union_sql}")


def create_dbt_clone_relation_when_requested(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    create: bool,
    rows: tuple[tuple[object, ...], ...] = ((1, "origin"),),
) -> None:
    """Create a dbt clone fixture relation when requested by a test case."""

    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
    if create:
        create_dbt_clone_relation(
            adapter=adapter,
            connection=connection,
            schema=schema,
            rows=rows,
        )


def read_dbt_clone_rows(
    *, adapter: DuckDbAdapter, connection: object, schema: str, name: str = "dbt_orders"
) -> tuple[tuple[object, ...], ...]:
    """Read deterministic dbt clone rows from DuckDB."""

    result: QueryResult = adapter.query(
        connection,
        f"SELECT order_id, status FROM {schema}.{name} ORDER BY order_id",
        limit=None,
    )
    return result.rows


def assert_dbt_clone_execution_result(
    *,
    result: CloneExecutionResult,
    expected_item_count: int,
    expected_action: str | None,
    expected_status: str | None,
) -> None:
    """Assert dbt clone execution result fields."""

    assert len(result.item_results) == expected_item_count
    if expected_item_count == 0:
        return
    assert result.item_results[0].action == expected_action
    assert result.item_results[0].status == expected_status


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
