"""Test helpers for planner helpers tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompiledSqlScenario,
    CompiledSqlTest,
    CompileModelConfig,
    CompileSqlReference,
    CompileSqlScenarioCte,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    SqlReferenceKind,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.scenario_artifacts import build_scenario_relation_map
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    ChangeDetectionResult,
    ScenarioArtifactIdentity,
    ScenarioRelationMap,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction
from sqlbuild.compiler.shared.helpers.hashing import compute_query_hash
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    BuildModelWarningsTestCase,
    IncrementalStrategyErrorTestCase,
    PlanAuditTestCase,
    PlanScenarioGraphErrorTestCase,
    PlanScenarioGraphTestCase,
    ResolveModelPlanActionTestCase,
)


def model_key(name: str) -> CompiledObjectKey:
    """Build a model object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name)


def source_key(name: str) -> CompiledObjectKey:
    """Build a source object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)


def seed_key(name: str) -> CompiledObjectKey:
    """Build a seed object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name)


def function_key(name: str) -> CompiledObjectKey:
    """Build a function object key."""

    return CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name=name)


def build_test_project(
    *,
    model_deps: dict[str, tuple[str, ...]] | None = None,
    model_paths: dict[str, str] | None = None,
    source_names: tuple[str, ...] = (),
    seed_names: tuple[str, ...] = (),
    function_names: tuple[str, ...] = (),
    sql_test_expected_model_names: tuple[str, ...] = (),
) -> CompiledProject:
    """Build a minimal CompiledProject for graph tests."""

    effective_paths: dict[str, str] = model_paths or {}
    source_name_set: set[str] = set(source_names)
    seed_name_set: set[str] = set(seed_names)
    function_name_set: set[str] = set(function_names)
    models: list[CompiledModel] = []
    model_name: str
    dep_names: tuple[str, ...]
    for model_name, dep_names in (model_deps or {}).items():
        deps: tuple[CompiledObjectKey, ...] = tuple(
            _resolve_dep_key(d, source_name_set, seed_name_set, function_name_set)
            for d in dep_names
        )
        rel_path: str = effective_paths.get(model_name, f"models/{model_name}.sql")
        models.append(
            CompiledModel(
                key=model_key(model_name),
                deps=deps,
                name=model_name,
                relative_path=Path(rel_path),
                query_sql=f"SELECT * FROM {model_name}",
                config=CompileModelConfig(),
                target=CompiledRelationTarget(
                    database=None, schema=None, name=model_name, qualified_name=None
                ),
            )
        )

    sources: list[CompiledSource] = []
    source_name: str
    for source_name in source_names:
        source_entry: SourceEntry = SourceEntry(
            name=source_name, schema="public", table=source_name
        )
        sources.append(
            CompiledSource(
                key=source_key(source_name),
                deps=(),
                name=source_name,
                source_entry=source_entry,
                source_file=DiscoveredSourceFile(
                    file_path=Path(f"sources/{source_name}.yml"),
                    relative_path=Path(source_name),
                    contents="",
                    source_entries=(source_entry,),
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name in seed_names:
        seeds.append(
            CompiledSeed(
                key=seed_key(seed_name),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=Path(f"seeds/{seed_name}.csv"),
                    relative_path=Path(f"seeds/{seed_name}.csv"),
                ),
                schema_entry=SchemaSeedEntry(name=seed_name, columns=()),
                schema_file=_stub_schema_file(),
                target=CompiledRelationTarget(
                    database=None, schema=None, name=seed_name, qualified_name=None
                ),
            )
        )

    functions: list[CompiledFunction] = []
    function_name: str
    for function_name in function_names:
        functions.append(
            CompiledFunction(
                key=function_key(function_name),
                deps=(),
                name=function_name,
                relative_path=Path(f"functions/sql/{function_name}.sql"),
                arguments=(),
                returns="BOOLEAN",
                body_sql="SELECT TRUE",
                target=CompiledRelationTarget(
                    database=None, schema=None, name=function_name, qualified_name=None
                ),
                fingerprint_target=CompiledRelationTarget(
                    database=None, schema=None, name=function_name, qualified_name=None
                ),
            )
        )

    sql_tests: list[CompiledSqlTest] = []
    if sql_test_expected_model_names:
        sql_tests.append(
            CompiledSqlTest(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SQL_TEST,
                    name="test_models",
                ),
                scope_deps=tuple(model_key(name) for name in sql_test_expected_model_names),
                name="test_models",
                test_file=DiscoveredSqlTestFile(
                    file_path=Path("tests/test_models.sql"),
                    relative_path=Path("tests/test_models.sql"),
                    contents="SELECT 1",
                    blocks=(),
                ),
                test_block=DiscoveredSqlTestBlock(
                    test_index=0,
                    header_values={},
                    sql_body="SELECT 1",
                ),
                sql_body="SELECT 1",
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        models=tuple(models),
        sources=tuple(sources),
        seeds=tuple(seeds),
        functions=tuple(functions),
        sql_tests=tuple(sql_tests),
    )


def build_snapshot_from_relation_names(relation_names: tuple[str, ...]) -> WarehouseSnapshot:
    """Build a minimal WarehouseSnapshot with the given relation names."""

    existing_relations: dict[str, RelationInfo] = {
        name: RelationInfo(database=None, schema="public", name=name, relation_type="BASE TABLE")
        for name in relation_names
    }
    return WarehouseSnapshot(existing_relations=existing_relations)


def build_scenario_from_test_case(
    test_case: PlanScenarioGraphTestCase | PlanScenarioGraphErrorTestCase,
) -> CompiledSqlScenario:
    """Build a minimal compiled SQL scenario from a graph test case."""

    scenario_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_SCENARIO,
        name="revenue__customer_refund",
    )
    assertion_ctes: tuple[CompileSqlScenarioCte, ...] = tuple(
        CompileSqlScenarioCte(name=f"__assert__assertion_{index}", sql_body=sql_body)
        for index, sql_body in enumerate(test_case.assertion_sql_bodies)
    )
    expected_ctes: tuple[CompileSqlScenarioCte, ...] = tuple(
        CompileSqlScenarioCte(name=f"__expected__{model_name}", sql_body="SELECT 1")
        for model_name in test_case.expected_model_names
    )
    return CompiledSqlScenario(
        key=scenario_key,
        name="revenue__customer_refund",
        scenario_file=DiscoveredSqlScenarioFile(
            file_path=Path("tests/scenarios/revenue__customer_refund.sql"),
            relative_path=Path("tests/scenarios/revenue__customer_refund.sql"),
            contents="",
            header_values={},
            name="revenue__customer_refund",
            sql_body="SELECT 1",
        ),
        sql_body="SELECT 1",
        expected_ctes=expected_ctes,
        assertion_ctes=assertion_ctes,
        source_fixture_names=test_case.source_fixture_names,
        ref_fixture_names=test_case.ref_fixture_names,
        seed_fixture_names=test_case.seed_fixture_names,
        expected_model_names=test_case.expected_model_names,
        assertion_names=tuple(cte.name.removeprefix("__assert__") for cte in assertion_ctes),
    )


def build_compiled_scenario_with_name(name: str) -> CompiledSqlScenario:
    """Build a minimal compiled SQL scenario with a specific name."""

    return CompiledSqlScenario(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=name,
        ),
        name=name,
        scenario_file=DiscoveredSqlScenarioFile(
            file_path=Path(f"tests/scenarios/{name}.sql"),
            relative_path=Path(f"tests/scenarios/{name}.sql"),
            contents="",
            header_values={},
            name=name,
            sql_body="SELECT 1",
        ),
        sql_body="SELECT 1",
    )


def build_scenario_relation_test_map() -> ScenarioRelationMap:
    """Build a relation map covering scenario relation planning tests."""

    return build_scenario_relation_map(
        scenario_name="revenue__customer_refund",
        hash_prefix="51b385aebe20",
        artifacts=(
            ScenarioArtifactIdentity(kind="source", logical_name="raw__orders"),
            ScenarioArtifactIdentity(kind="ref", logical_name="stg_customers"),
            ScenarioArtifactIdentity(kind="seed", logical_name="country_codes"),
            ScenarioArtifactIdentity(kind="model", logical_name="daily_revenue"),
            ScenarioArtifactIdentity(kind="model", logical_name="customer_revenue"),
        ),
    )


def build_scenario_relation_test_project() -> CompiledProject:
    """Build a project covering scenario relation planning tests."""

    return build_test_project(
        model_deps={
            "daily_revenue": ("raw__orders", "stg_customers", "country_codes"),
            "customer_revenue": ("raw__orders",),
            "stg_customers": ("raw__orders",),
        },
        source_names=("raw__orders",),
        seed_names=("country_codes",),
    )


def build_test_project_with_source_entry(source_entry: SourceEntry) -> CompiledProject:
    """Build a minimal CompiledProject containing one source entry."""

    source: CompiledSource = CompiledSource(
        key=source_key(source_entry.name),
        deps=(),
        name=source_entry.name,
        source_entry=source_entry,
        source_file=DiscoveredSourceFile(
            file_path=Path("sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents="",
            source_entries=(source_entry,),
        ),
    )
    return CompiledProject(
        run_id="test_run",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        sources=(source,),
    )


def _resolve_dep_key(
    name: str,
    source_names: set[str],
    seed_names: set[str],
    function_names: set[str],
) -> CompiledObjectKey:
    """Resolve a dependency name to the correct key type."""

    if name in source_names:
        return source_key(name)
    if name in seed_names:
        return seed_key(name)
    if name in function_names:
        return function_key(name)
    return model_key(name)


def build_strategy_model(test_case: ResolveModelPlanActionTestCase) -> CompiledModel:
    """Build a CompiledModel from an action resolution test case."""

    config_values: dict[str, object] = {"materialized": test_case.materialized}
    if test_case.incremental_strategy is not None:
        config_values["incremental_strategy"] = test_case.incremental_strategy
    if test_case.enabled is not None:
        config_values["enabled"] = test_case.enabled
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="test_model"),
        deps=(),
        name="test_model",
        relative_path=Path("models/test_model.sql"),
        query_sql="SELECT 1",
        config=CompileModelConfig(values=config_values),
        target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="test_model",
            qualified_name="staging.test_model",
        ),
    )


def build_strategy_change_result(
    test_case: ResolveModelPlanActionTestCase,
) -> ChangeDetectionResult:
    """Build a ChangeDetectionResult from an action resolution test case."""

    return ChangeDetectionResult(
        model_name="test_model",
        change_kind=test_case.change_kind,
        query_changed=test_case.query_changed,
        schema_findings=test_case.schema_findings,
        backfill=BackfillResult(
            action=test_case.backfill_action,
            duration=test_case.backfill_duration,
        ),
    )


def build_strategy_error_model(test_case: IncrementalStrategyErrorTestCase) -> CompiledModel:
    """Build a CompiledModel from a strategy error test case."""

    config_values: dict[str, object] = {"materialized": test_case.materialized}
    if test_case.incremental_strategy is not None:
        config_values["incremental_strategy"] = test_case.incremental_strategy
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="test_model"),
        deps=(),
        name="test_model",
        relative_path=Path("models/test_model.sql"),
        query_sql="SELECT 1",
        config=CompileModelConfig(values=config_values),
        target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="test_model",
            qualified_name="staging.test_model",
        ),
    )


def build_strategy_error_change_result(
    test_case: IncrementalStrategyErrorTestCase,
) -> ChangeDetectionResult:
    """Build a ChangeDetectionResult from a strategy error test case."""

    return ChangeDetectionResult(
        model_name="test_model",
        change_kind=test_case.change_kind,
        query_changed=False,
        schema_findings=(),
        backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
    )


def build_warnings_change_result(
    test_case: BuildModelWarningsTestCase,
) -> ChangeDetectionResult:
    """Build a ChangeDetectionResult from a warnings test case."""

    return ChangeDetectionResult(
        model_name=test_case.model_name,
        change_kind=test_case.change_kind,
        query_changed=test_case.query_changed,
        schema_findings=test_case.schema_findings,
        backfill=BackfillResult(action=test_case.backfill_action),
    )


def build_audit_from_test_case(
    test_case: PlanAuditTestCase,
) -> CompiledAudit:
    """Build a minimal CompiledAudit from a test case."""

    return CompiledAudit(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name="test_audit"),
        scope_deps=(),
        name="test_audit",
        audit_file=DiscoveredAuditFile(
            file_path=Path("audits/generic/test.sql"),
            relative_path=Path("audits/generic/test.sql"),
            contents="",
            blocks=(),
        ),
        audit_block=DiscoveredAuditBlock(audit_index=0, header_values={}, sql_body=""),
        sql_body=test_case.sql_body,
    )


def build_audit_model_targets(
    targets: dict[str, str],
) -> dict[str, CompiledRelationTarget]:
    """Build model target lookup from name -> qualified_name."""

    return {
        name: CompiledRelationTarget(
            database=None,
            schema=None,
            name=name,
            qualified_name=qualified,
        )
        for name, qualified in targets.items()
    }


def build_audit_source_map(
    entries: dict[str, tuple[str | None, str, str | None]],
) -> dict[str, SourceEntry]:
    """Build source map from name -> (database, schema, table)."""

    return {
        name: SourceEntry(
            name=name,
            database=parts[0],
            schema=parts[1],
            table=parts[2],
        )
        for name, parts in entries.items()
    }


def build_cursor_ref(ref_name: str) -> CompileSqlReference:
    """Build a ref-type SQL reference for cursor resolution tests."""

    return CompileSqlReference(
        ref_kind=SqlReferenceKind.REF,
        ref_name=ref_name,
    )


def build_cursor_model_map(
    ref_name: str,
    qualified_name: str | None,
) -> dict[str, CompiledModel]:
    """Build a model map with one entry for cursor resolution tests."""

    if qualified_name is None:
        return {}
    return {
        ref_name: CompiledModel(
            key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=ref_name),
            deps=(),
            name=ref_name,
            relative_path=Path(f"models/{ref_name}.sql"),
            query_sql="SELECT 1",
            config=CompileModelConfig(),
            target=CompiledRelationTarget(
                database=None,
                schema=None,
                name=ref_name,
                qualified_name=qualified_name,
            ),
        ),
    }


def build_cursor_deferred_targets(
    ref_name: str,
    qualified_name: str | None,
) -> dict[str, CompiledRelationTarget] | None:
    """Build deferred targets dict with one entry, or None."""

    if qualified_name is None:
        return None
    return {
        ref_name: CompiledRelationTarget(
            database=None,
            schema=None,
            name=ref_name,
            qualified_name=qualified_name,
        ),
    }


def build_cursor_override_model(cursor_type: str | None) -> CompiledModel:
    """Build a minimal model with optional cursor_type for override resolution tests."""

    config_values: dict[str, object] = {"materialized": "incremental"}
    if cursor_type is not None:
        config_values["cursor_type"] = cursor_type
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="test_model"),
        deps=(),
        name="test_model",
        relative_path=Path("models/test_model.sql"),
        query_sql="SELECT 1",
        config=CompileModelConfig(values=config_values),
        target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="test_model",
            qualified_name="staging.test_model",
        ),
    )


def build_microbatch_lookback_model(
    *,
    incremental_strategy: str,
    batch_size: str,
    lookback: str | None,
) -> CompiledModel:
    """Build a microbatch model for lookback resolution tests."""

    config_values: dict[str, object] = {
        "materialized": "incremental",
        "incremental_strategy": incremental_strategy,
        "incremental_mode": "microbatch",
        "batch_size": batch_size,
    }
    if lookback is not None:
        config_values["lookback"] = lookback
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="test_model"),
        deps=(),
        name="test_model",
        relative_path=Path("models/test_model.sql"),
        query_sql="SELECT 1",
        config=CompileModelConfig(values=config_values),
        target=CompiledRelationTarget(
            database=None,
            schema="staging",
            name="test_model",
            qualified_name="staging.test_model",
        ),
    )


def build_cascade_upstream_state(
    entries: tuple[tuple[str, BackfillAction, str | None, str | None], ...],
) -> tuple[
    tuple[CompiledObjectKey, ...],
    dict[str, CascadeResult],
    dict[str, str | None],
]:
    """Build upstream keys, effective cascades, and cursor types from test tuples.

    Each tuple is (model_name, effective_action, effective_duration, cursor_type).
    """

    keys: list[CompiledObjectKey] = []
    cascades: dict[str, CascadeResult] = {}
    cursor_types: dict[str, str | None] = {}
    name: str
    action: BackfillAction
    duration: str | None
    cursor_type: str | None
    for name, action, duration, cursor_type in entries:
        keys.append(model_key(name))
        cascades[name] = CascadeResult(
            effective_action=action,
            effective_duration=duration,
            root_cause=None,
            causes=(),
        )
        cursor_types[name] = cursor_type
    return tuple(keys), cascades, cursor_types


def build_compiled_function(
    *, body_sql: str, query_change_backfill: str | None = None, target_schema: str = "main"
) -> CompiledFunction:
    """Build a minimal compiled function for planner tests."""

    return CompiledFunction(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.FUNCTION,
            name="is_completed_order",
        ),
        deps=(),
        name="is_completed_order",
        relative_path=Path("functions/sql/is_completed_order.sql"),
        arguments=(FunctionArgument(name="order_status", type="STRING"),),
        returns="BOOLEAN",
        body_sql=body_sql,
        target=CompiledRelationTarget(
            database=None,
            schema=target_schema,
            name="is_completed_order",
            qualified_name=f"{target_schema}.is_completed_order",
        ),
        fingerprint_target=CompiledRelationTarget(
            database=None,
            schema=target_schema,
            name="is_completed_order",
            qualified_name=f"{target_schema}.is_completed_order",
        ),
        query_change_backfill=query_change_backfill,
    )


def build_fingerprint(*, query_sql: str) -> Fingerprint:
    """Build a fingerprint with a hash matching the supplied query SQL."""

    return Fingerprint(
        model_name="is_completed_order",
        target_database=None,
        target_schema="main",
        target_name="is_completed_order",
        run_id="run-1",
        query_hash=compute_query_hash(query_sql),
        ast_hash=None,
        schema_fingerprint="",
        query_sql=query_sql,
        ts=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _stub_schema_file() -> DiscoveredSchemaFile:
    """Return a minimal schema file stub for seed construction."""

    return DiscoveredSchemaFile(
        file_path=Path("seeds/schema.yml"),
        relative_path=Path("seeds/schema.yml"),
        contents="",
        model_entries=(),
        seed_entries=(),
    )


def build_scheduling_audit(
    *,
    references: tuple[CompileSqlReference, ...],
    attached_target_kind: AttachedAuditTargetKind | None,
    attached_target_name: str | None,
) -> CompiledAudit:
    """Build a minimal CompiledAudit for scheduling tests."""

    stub_file: DiscoveredAuditFile = DiscoveredAuditFile(
        file_path=Path("audits/singular/check.sql"),
        relative_path=Path("audits/singular/check.sql"),
        contents="",
        blocks=(),
    )
    stub_block: DiscoveredAuditBlock = DiscoveredAuditBlock(
        audit_index=0,
        header_values={},
        sql_body="",
    )
    name: str = "test_audit"
    return CompiledAudit(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        scope_deps=(),
        name=name,
        audit_file=stub_file,
        audit_block=stub_block,
        sql_body="SELECT 1",
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        severity="warn",
        run_scope="final",
    )


def build_scheduling_graph(
    edges: dict[str, tuple[str, ...]],
) -> tuple[
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
]:
    """Build upstream and downstream dep dicts from simple name-based edges."""

    from sqlbuild.compiler.planner.helpers.graph import build_downstream_deps

    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    name: str
    deps: tuple[str, ...]
    for name, deps in edges.items():
        key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL, name=name
        )
        upstream[key] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in deps
        )
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream
    )
    return upstream, downstream
