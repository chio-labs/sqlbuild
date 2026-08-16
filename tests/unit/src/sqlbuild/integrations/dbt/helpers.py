from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompiledSqlTest,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
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
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.clone.models import CloneExecutionResult
from sqlbuild.integrations.dbt._helpers.cli.runner import build_dbt_ls_argv
from sqlbuild.integrations.dbt._helpers.graph.core import (
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt._helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliConfigOverrides,
    DbtCliOptions,
    DbtCombinedGraphKey,
    DbtCommandResult,
    DbtLsNode,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
)
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, SchemaSeedEntry, SourceEntry


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


def emit_connection_progress(**kwargs: object) -> None:
    """Emit one successful connection progress cycle from a mocked planner."""

    hooks: object = kwargs["hooks"]
    start: object = getattr(hooks, "on_connection_start", None)
    complete: object = getattr(hooks, "on_connection_complete", None)
    assert callable(start)
    assert callable(complete)
    on_start: Callable[[int], None] = cast(Callable[[int], None], start)
    on_complete: ConnectionElapsedCallback = cast(ConnectionElapsedCallback, complete)
    on_start(1)
    on_complete(1, elapsed_seconds=0.0)


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
    target_model_name: str = "fact_orders",
) -> DbtManifestIndex:
    """Build a manifest fixture for dbt SQL test target adaptation."""

    fact_node: dict[str, object] = build_manifest_model_node(
        unique_id=f"model.analytics.{target_model_name}",
        package_name="analytics",
        name=target_model_name,
        relation_name=f'"analytics"."{target_model_name}"',
        raw_code="select * from {{ ref('stg_orders') }}",
        compiled_code=fact_compiled_code,
        depends_on_nodes=("model.analytics.stg_orders",),
    )
    nodes: tuple[dict[str, object], ...] = (
        build_manifest_model_node(
            unique_id="model.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name=dep_relation_name,
            compiled_code="select * from raw.orders",
        ),
        fact_node,
        *(
            build_manifest_model_node(
                unique_id="model.finance.fact_orders",
                package_name="finance",
                name="fact_orders",
                relation_name='"finance"."fact_orders"',
                compiled_code="select 1 as order_id",
            ),
        )
        * int(include_ambiguous_package),
    )
    return build_dbt_manifest_index(raw_data=build_manifest_data(nodes=nodes))


def build_dbt_sql_test_target_success_manifest(*, manifest_kind: str) -> DbtManifestIndex:
    """Build a success manifest variant for dbt SQL test target tests."""

    return _DBT_SQL_TEST_SUCCESS_MANIFEST_FACTORIES[manifest_kind]()


def build_dbt_sql_test_target_error_manifest(*, manifest_kind: str) -> DbtManifestIndex:
    """Build an error manifest variant for dbt SQL test target tests."""

    return _DBT_SQL_TEST_ERROR_MANIFEST_FACTORIES[manifest_kind]()


def build_dbt_sql_test_source_seed_manifest(
    *,
    dependency_kind: str,
    relation_name: str | None = None,
    compiled_code: str | None = None,
    include_ambiguous_package: bool = False,
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a source or seed dependency."""

    dependency_unique_ids: dict[str, str] = {
        "source": "source.analytics.raw.orders",
        "seed": "seed.analytics.countries",
    }
    default_relation_names: dict[str, str] = {
        "source": '"raw"."orders"',
        "seed": '"analytics"."countries"',
    }
    default_compiled_codes: dict[str, str] = {
        "source": 'select * from "raw"."orders"',
        "seed": 'select * from "analytics"."countries"',
    }
    resolved_relation_name: str = relation_name or default_relation_names[dependency_kind]
    resolved_compiled_code: str = compiled_code or default_compiled_codes[dependency_kind]
    source_nodes_by_kind: dict[str, tuple[dict[str, object], ...]] = {
        "source": (
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                package_name="analytics",
                source_name="raw",
                name="orders",
                relation_name=resolved_relation_name,
            ),
            *(
                build_manifest_source_node(
                    unique_id="source.finance.raw.orders",
                    package_name="finance",
                    source_name="raw",
                    name="orders",
                    relation_name='"finance_raw"."orders"',
                ),
            )
            * int(include_ambiguous_package),
        ),
        "seed": (),
    }
    seed_nodes_by_kind: dict[str, tuple[dict[str, object], ...]] = {
        "source": (),
        "seed": (
            build_manifest_seed_node(
                unique_id="seed.analytics.countries",
                package_name="analytics",
                name="countries",
                relation_name=resolved_relation_name,
            ),
            *(
                build_manifest_seed_node(
                    unique_id="seed.finance.countries",
                    package_name="finance",
                    name="countries",
                    relation_name='"finance"."countries"',
                ),
            )
            * int(include_ambiguous_package),
        ),
    }
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    relation_name='"analytics"."fact_orders"',
                    compiled_code=resolved_compiled_code,
                    depends_on_nodes=(dependency_unique_ids[dependency_kind],),
                ),
                *seed_nodes_by_kind[dependency_kind],
            ),
            sources=source_nodes_by_kind[dependency_kind],
        )
    )


def build_dbt_sql_test_source_manifest(
    *,
    relation_name: str | None = None,
    compiled_code: str | None = None,
    include_ambiguous_package: bool = False,
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a source dependency."""

    return build_dbt_sql_test_source_seed_manifest(
        dependency_kind="source",
        relation_name=relation_name,
        compiled_code=compiled_code,
        include_ambiguous_package=include_ambiguous_package,
    )


def build_dbt_sql_test_seed_manifest(
    *,
    relation_name: str | None = None,
    compiled_code: str | None = None,
    include_ambiguous_package: bool = False,
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a seed dependency."""

    return build_dbt_sql_test_source_seed_manifest(
        dependency_kind="seed",
        relation_name=relation_name,
        compiled_code=compiled_code,
        include_ambiguous_package=include_ambiguous_package,
    )


def build_dbt_sql_test_model_chain_manifest(
    *, dependency_kind: str, upstream_compiled_code: str | None | object = "default"
) -> DbtManifestIndex:
    """Build a dbt SQL test manifest with a dbt model chain."""

    default_compiled_codes: dict[str, str] = {
        "source": 'select order_id from "raw"."orders"',
        "seed": 'select country_code from "analytics"."countries"',
    }
    compiled_codes_by_default_state: dict[bool, str | None] = {
        True: default_compiled_codes[dependency_kind],
        False: cast(str | None, upstream_compiled_code),
    }
    dependency_unique_ids: dict[str, str] = {
        "source": "source.analytics.raw.orders",
        "seed": "seed.analytics.countries",
    }
    source_nodes_by_kind: dict[str, tuple[dict[str, object], ...]] = {
        "source": (
            build_manifest_source_node(
                unique_id="source.analytics.raw.orders",
                package_name="analytics",
                source_name="raw",
                name="orders",
                relation_name='"raw"."orders"',
            ),
        ),
        "seed": (),
    }
    seed_nodes_by_kind: dict[str, tuple[dict[str, object], ...]] = {
        "source": (),
        "seed": (
            build_manifest_seed_node(
                unique_id="seed.analytics.countries",
                package_name="analytics",
                name="countries",
                relation_name='"analytics"."countries"',
            ),
        ),
    }
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.stg_orders",
                    package_name="analytics",
                    name="stg_orders",
                    relation_name='"analytics"."stg_orders"',
                    compiled_code=compiled_codes_by_default_state[
                        upstream_compiled_code == "default"
                    ],
                    depends_on_nodes=(dependency_unique_ids[dependency_kind],),
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    relation_name='"analytics"."fact_orders"',
                    compiled_code='select order_id from "analytics"."stg_orders"',
                    depends_on_nodes=("model.analytics.stg_orders",),
                ),
                *seed_nodes_by_kind[dependency_kind],
            ),
            sources=source_nodes_by_kind[dependency_kind],
        )
    )


def build_dbt_sql_test_source_chain_manifest(
    *, upstream_compiled_code: str | None | object = "default"
) -> DbtManifestIndex:
    """Build a dbt model chain ending at a source dependency."""

    return build_dbt_sql_test_model_chain_manifest(
        dependency_kind="source",
        upstream_compiled_code=upstream_compiled_code,
    )


def build_dbt_sql_test_seed_chain_manifest() -> DbtManifestIndex:
    """Build a dbt model chain ending at a seed dependency."""

    return build_dbt_sql_test_model_chain_manifest(dependency_kind="seed")


def build_dbt_sql_test_boundary_chain_manifest(*, boundary_kind: str) -> DbtManifestIndex:
    """Build a dbt chain manifest whose intermediate node is a snapshot or ephemeral."""

    intermediate_nodes: dict[str, dict[str, object]] = {
        "ephemeral": build_manifest_model_node(
            unique_id="model.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name='"analytics"."stg_orders"',
            compiled_code='select order_id from "raw"."orders"',
            materialized="ephemeral",
            depends_on_nodes=("source.analytics.raw.orders",),
        ),
        "snapshot": build_manifest_model_node(
            unique_id="snapshot.analytics.stg_orders",
            package_name="analytics",
            name="stg_orders",
            relation_name='"analytics"."stg_orders"',
            compiled_code='select order_id from "raw"."orders"',
            resource_type="snapshot",
            materialized="table",
            depends_on_nodes=("source.analytics.raw.orders",),
        ),
    }
    intermediate_node: dict[str, object] = intermediate_nodes[boundary_kind]
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


def build_dbt_sql_test_snapshot_chain_manifest() -> DbtManifestIndex:
    """Build a dbt model chain with a snapshot boundary."""

    return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="snapshot")


def build_dbt_sql_test_ephemeral_chain_manifest() -> DbtManifestIndex:
    """Build a dbt model chain with an ephemeral boundary."""

    return build_dbt_sql_test_boundary_chain_manifest(boundary_kind="ephemeral")


def build_dbt_sql_test_target_missing_compiled_manifest() -> DbtManifestIndex:
    """Build a dbt target manifest without compiled SQL for the target."""

    return build_dbt_sql_test_target_manifest(fact_compiled_code=None)


_DBT_SQL_TEST_SUCCESS_MANIFEST_FACTORIES: MappingProxyType[str, Callable[[], DbtManifestIndex]] = (
    MappingProxyType(
        {
            "default": build_dbt_sql_test_target_manifest,
            "source_dependency": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="source"
            ),
            "source_unquoted": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="source",
                relation_name="raw.orders",
                compiled_code="select * from raw.orders",
            ),
            "source_three_part": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="source",
                relation_name='"warehouse"."raw"."orders"',
                compiled_code='select * from "warehouse"."raw"."orders"',
            ),
            "source_alias": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="source",
                relation_name='"raw"."orders_alias"',
                compiled_code='select * from "raw"."orders_alias"',
            ),
            "source_ambiguous_fixture": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="source",
                include_ambiguous_package=True,
            ),
            "chain_source_dependency": partial(
                build_dbt_sql_test_model_chain_manifest, dependency_kind="source"
            ),
            "seed_dependency": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="seed"
            ),
            "seed_unquoted": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="seed",
                relation_name="analytics.countries",
                compiled_code="select * from analytics.countries",
            ),
            "seed_three_part": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="seed",
                relation_name='"warehouse"."analytics"."countries"',
                compiled_code='select * from "warehouse"."analytics"."countries"',
            ),
            "seed_alias": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="seed",
                relation_name='"analytics"."countries_alias"',
                compiled_code='select * from "analytics"."countries_alias"',
            ),
            "seed_ambiguous_fixture": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="seed",
                include_ambiguous_package=True,
            ),
            "chain_seed_dependency": partial(
                build_dbt_sql_test_model_chain_manifest, dependency_kind="seed"
            ),
            "chain_snapshot_boundary": partial(
                build_dbt_sql_test_boundary_chain_manifest, boundary_kind="snapshot"
            ),
            "chain_ephemeral_boundary": partial(
                build_dbt_sql_test_boundary_chain_manifest, boundary_kind="ephemeral"
            ),
            "unquoted": partial(
                build_dbt_sql_test_target_manifest,
                dep_relation_name="analytics.stg_orders",
                fact_compiled_code="select * from analytics.stg_orders where amount_cents > 0",
            ),
            "three_part": partial(
                build_dbt_sql_test_target_manifest,
                dep_relation_name='"warehouse"."analytics"."stg_orders"',
                fact_compiled_code=(
                    'select * from "warehouse"."analytics"."stg_orders" where amount_cents > 0'
                ),
            ),
            "alias": partial(
                build_dbt_sql_test_target_manifest,
                dep_relation_name='"analytics"."stg_orders_alias"',
                fact_compiled_code='select * from "analytics"."stg_orders_alias"',
            ),
            "ambiguous": partial(
                build_dbt_sql_test_target_manifest, include_ambiguous_package=True
            ),
            "relation_in_string_and_comment": partial(
                build_dbt_sql_test_target_manifest,
                dep_relation_name="analytics.stg_orders",
                fact_compiled_code=(
                    "-- upstream analytics.stg_orders\n"
                    "select *, 'analytics.stg_orders' as src "
                    "from analytics.stg_orders where amount_cents > 0"
                ),
            ),
        }
    )
)
_DBT_SQL_TEST_ERROR_MANIFEST_FACTORIES: MappingProxyType[str, Callable[[], DbtManifestIndex]] = (
    MappingProxyType(
        {
            "default": partial(
                build_dbt_sql_test_target_manifest,
                fact_compiled_code="select * from analytics.unexpected_orders",
            ),
            "source_dependency": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="source"
            ),
            "source_ambiguous_fixture": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="source"
            ),
            "source_unresolved_relation": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="source",
                compiled_code="select * from raw.unexpected_orders",
            ),
            "chain_missing_compiled_sql": partial(
                build_dbt_sql_test_model_chain_manifest,
                dependency_kind="source",
                upstream_compiled_code=None,
            ),
            "chain_unresolved_relation": partial(
                build_dbt_sql_test_model_chain_manifest,
                dependency_kind="source",
                upstream_compiled_code="select * from raw.unexpected_orders",
            ),
            "chain_snapshot_boundary": partial(
                build_dbt_sql_test_boundary_chain_manifest, boundary_kind="snapshot"
            ),
            "chain_ephemeral_boundary": partial(
                build_dbt_sql_test_boundary_chain_manifest, boundary_kind="ephemeral"
            ),
            "seed_dependency": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="seed"
            ),
            "seed_ambiguous_fixture": partial(
                build_dbt_sql_test_source_seed_manifest, dependency_kind="seed"
            ),
            "seed_unresolved_relation": partial(
                build_dbt_sql_test_source_seed_manifest,
                dependency_kind="seed",
                compiled_code="select * from analytics.unexpected_countries",
            ),
            "ambiguous": partial(
                build_dbt_sql_test_target_manifest, include_ambiguous_package=True
            ),
            "missing_compiled_sql": partial(
                build_dbt_sql_test_target_manifest, fact_compiled_code=None
            ),
        }
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

    return _DBT_SQL_TEST_ERROR_PROJECT_FACTORIES[project_kind]()


_DBT_SQL_TEST_ERROR_PROJECT_FACTORIES: MappingProxyType[str, Callable[[], CompiledProject]] = (
    MappingProxyType(
        {
            "default": partial(
                build_project_with_expected_sql_test_targets,
                expected_model_names=("fact_orders",),
            ),
            "model_name_collision": partial(
                build_project_with_expected_sql_test_targets,
                expected_model_names=("fact_orders",),
                sqlbuild_model_names=("fact_orders",),
            ),
            "source_relation_collision": build_project_with_source_relation_collision,
            "seed_relation_collision": build_project_with_seed_relation_collision,
            "seed_relation_collision_unqualified": partial(
                build_project_with_seed_relation_collision, qualified_name=None
            ),
        }
    )
)


def resolve_dbt_sql_test_fixture_names(
    *,
    manifest: DbtManifestIndex,
    fixture_kind: str,
    known_names: set[str],
) -> set[str]:
    """Resolve dbt-backed SQL test fixture names for a source or seed."""

    resolver: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=manifest)
    fixture_resolvers: dict[str, Callable[..., set[str]]] = {
        "model": resolver.extend_sql_test_model_names,
        "source": resolver.extend_sql_test_source_names,
        "seed": resolver.extend_sql_test_seed_names,
    }
    fixture_keywords: dict[str, str] = {
        "model": "known_model_names",
        "source": "known_source_names",
        "seed": "known_seed_names",
    }
    return fixture_resolvers[fixture_kind](**{fixture_keywords[fixture_kind]: known_names})


def resolve_dbt_sql_test_model_fixture_names(
    manifest: DbtManifestIndex, known_names: set[str]
) -> set[str]:
    """Resolve dbt-backed model fixture names."""

    resolver: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=manifest)
    return resolver.extend_sql_test_model_names(known_model_names=known_names)


def resolve_dbt_sql_test_source_fixture_names(
    manifest: DbtManifestIndex, known_names: set[str]
) -> set[str]:
    """Resolve dbt-backed source fixture names."""

    resolver: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=manifest)
    return resolver.extend_sql_test_source_names(known_source_names=known_names)


def resolve_dbt_sql_test_seed_fixture_names(
    manifest: DbtManifestIndex, known_names: set[str]
) -> set[str]:
    """Resolve dbt-backed seed fixture names."""

    resolver: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=manifest)
    return resolver.extend_sql_test_seed_names(known_seed_names=known_names)


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

    model_node: dict[str, object] = build_manifest_model_node(
        unique_id="model.analytics.dbt_orders",
        package_name="analytics",
        name="dbt_orders",
        relation_name="prod.dbt_orders",
        schema="prod",
        alias="dbt_orders",
        materialized=materialized,
        raw_code="{{ config(materialized='view') }}\nSELECT 99 AS order_id, 'raw' AS status",
    )
    return build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=(model_node,) * int(include_model))
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

    adapter.execute(connection=connection, sql=f"CREATE SCHEMA IF NOT EXISTS {schema}")
    selects: list[str] = []
    row: tuple[object, ...]
    for row in rows:
        order_id: int = cast(int, row[0])
        status: str = cast(str, row[1])
        selects.append(f"SELECT {order_id} AS order_id, '{status}' AS status")
    union_sql: str = " UNION ALL ".join(selects)
    adapter.execute(
        connection=connection, sql=f"CREATE OR REPLACE TABLE {schema}.{name} AS {union_sql}"
    )


def create_dbt_clone_relation_when_requested(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    schema: str,
    create: bool,
    rows: tuple[tuple[object, ...], ...] = ((1, "origin"),),
) -> None:
    """Create a dbt clone fixture relation when requested by a test case."""

    adapter.execute(connection=connection, sql=f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for _requested_relation in range(int(create)):
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
        connection=connection,
        sql=f"SELECT order_id, status FROM {schema}.{name} ORDER BY order_id",
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
    actual_outcomes: tuple[tuple[str, str], ...] = tuple(
        (item.action, item.status) for item in result.item_results
    )
    assert actual_outcomes == ((expected_action, expected_status),) * expected_item_count
