"""Scenario relation override planning helpers."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSqlScenario,
    CompileSqlScenarioCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.function_fingerprints import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner.helpers.graph import build_upstream_deps, topologically_order_keys
from sqlbuild.compiler.planner.helpers.plan_entry import extract_seed_columns, plan_model
from sqlbuild.compiler.planner.helpers.resolve.refs import build_function_locations
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_function_sql
from sqlbuild.compiler.planner.models import (
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanWarning,
    ScenarioArtifactIdentity,
    ScenarioAssertionExpectationPlan,
    ScenarioExecutionPlan,
    ScenarioExpectedExpectationPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
    SeedPlanEntry,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.shared.constants import (
    SCENARIO_PLAN_INTERNAL,
    SCENARIO_PLAN_MISSING_FIXTURE_SQL,
    SCENARIO_PLAN_MISSING_RELATION_TARGET,
    SCENARIO_PLAN_SQLGLOT_PARSE,
    SCENARIO_PLAN_SQLGLOT_UNAVAILABLE,
    SCENARIO_PLAN_UNKNOWN_SEED,
)
from sqlbuild.shared.helpers.diagnostics_logging import log_debug_event
from sqlbuild.shared.helpers.polyglot import import_polyglot_sql
from sqlbuild.shared.helpers.sql_reference_patterns import reference_call_prefix_pattern_text
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.source import SourceEntry

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")
_REF_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.REF)}\s*"
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)
_SEED_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.SEED)}\s*"
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)
_SOURCE_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.SOURCE)}\s*"
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(
    rf'{reference_call_prefix_pattern_text(SqlReferenceKind.DBT_REF)}\s*["\']'
    r'(?P<first>[A-Za-z_][A-Za-z0-9_]*)["\']\s*'
    r'(?:,\s*["\'](?P<second>[A-Za-z_][A-Za-z0-9_]*)["\']\s*)?\)'
)


def build_scenario_relation_plan(
    *,
    project: CompiledProject,
    graph_plan: ScenarioGraphPlan,
    relation_map: ScenarioRelationMap,
    database: str | None = None,
    schema: str | None = None,
) -> ScenarioRelationPlan:
    """Build scenario-scoped relation locations and source entries."""

    artifacts: dict[ScenarioArtifactIdentity, str] = {
        artifact.identity: artifact.physical_name for artifact in relation_map.artifacts
    }
    source_entries: dict[str, SourceEntry] = {
        source.name: source.source_entry for source in project.sources
    }

    model_locations: dict[str, CompiledRelationLocation] = {}
    source_fixture_locations: dict[str, CompiledRelationLocation] = {}
    ref_fixture_locations: dict[str, CompiledRelationLocation] = {}
    dbt_ref_fixture_locations: dict[str, CompiledRelationLocation] = {}
    seed_fixture_locations: dict[str, CompiledRelationLocation] = {}
    seed_locations: dict[str, CompiledRelationLocation] = {}
    source_map: dict[str, SourceEntry] = {}

    model_name: str
    for model_name in graph_plan.model_names:
        model_locations[model_name] = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.MODEL,
            logical_name=model_name,
            database=database,
            schema=schema,
        )

    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        target: CompiledRelationLocation = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.REF,
            logical_name=ref_name,
            database=database,
            schema=schema,
        )
        ref_fixture_locations[ref_name] = target
        model_locations[ref_name] = target

    source_name: str
    for source_name in graph_plan.source_fixture_names:
        target = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.SOURCE,
            logical_name=source_name,
            database=database,
            schema=schema,
        )
        source_fixture_locations[source_name] = target
        source_entry: SourceEntry = source_entries[source_name]
        source_map[source_name] = replace(
            source_entry,
            database=target.database,
            schema=target.schema,
            table=target.name,
            expression=None,
            type_enforcement=False,
        )

    dbt_ref_name: str
    for dbt_ref_name in graph_plan.dbt_ref_fixture_names:
        dbt_ref_fixture_locations[dbt_ref_name] = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.DBT_REF,
            logical_name=dbt_ref_name,
            database=database,
            schema=schema,
        )

    seed_name: str
    for seed_name in graph_plan.seed_names:
        target = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.SEED,
            logical_name=seed_name,
            database=database,
            schema=schema,
        )
        seed_locations[seed_name] = target

    for seed_name in graph_plan.seed_fixture_names:
        seed_fixture_locations[seed_name] = _required_target(
            seed_locations,
            seed_name,
            kind=ScenarioArtifactKind.SEED,
        )

    return ScenarioRelationPlan(
        scenario_name=graph_plan.name,
        relation_map=relation_map,
        model_locations=model_locations,
        seed_locations=seed_locations,
        project_source_map=source_entries,
        source_map=source_map,
        source_fixture_locations=source_fixture_locations,
        ref_fixture_locations=ref_fixture_locations,
        dbt_ref_fixture_locations=dbt_ref_fixture_locations,
        seed_fixture_locations=seed_fixture_locations,
    )


def resolve_scenario_check_sql(
    *,
    sql: str,
    relation_plan: ScenarioRelationPlan,
    sql_analysis_enabled: bool = True,
    sql_analysis_dialect: str | None = None,
) -> str:
    """Resolve refs, seeds, and sources in scenario expected/assertion SQL."""

    if sql_analysis_enabled:
        return _resolve_scenario_check_sql_with_sql_analysis(
            sql=sql,
            relation_plan=relation_plan,
            sql_analysis_dialect=sql_analysis_dialect,
        )

    def _replace_ref(match: re.Match[str]) -> str:
        target: CompiledRelationLocation | None = relation_plan.model_locations.get(
            match.group("name")
        )
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    def _replace_seed(match: re.Match[str]) -> str:
        target: CompiledRelationLocation | None = relation_plan.seed_locations.get(
            match.group("name")
        )
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    def _replace_source(match: re.Match[str]) -> str:
        source: SourceEntry | None = relation_plan.source_map.get(match.group("name"))
        if source is None:
            return match.group(0)
        return render_source_relation(source)

    def _replace_dbt_ref(match: re.Match[str]) -> str:
        target: CompiledRelationLocation | None = relation_plan.dbt_ref_fixture_locations.get(
            _dbt_ref_fixture_name(match)
        )
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    result: str = _REF_PATTERN.sub(_replace_ref, sql)
    result = _SEED_PATTERN.sub(_replace_seed, result)
    result = _SOURCE_PATTERN.sub(_replace_source, result)
    return _DBT_REF_PATTERN.sub(_replace_dbt_ref, result)


def build_scenario_execution_plan(
    *,
    scenario: CompiledSqlScenario,
    project: CompiledProject,
    adapter: BaseAdapter,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
    snapshot: WarehouseSnapshot | None = None,
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] | None = None,
    sql_analysis_enabled: bool = True,
    sql_analysis_dialect: str | None = None,
) -> tuple[ScenarioExecutionPlan, tuple[PlanWarning, ...]]:
    """Build a dry-run execution plan for one SQL scenario."""

    effective_snapshot: WarehouseSnapshot = snapshot or WarehouseSnapshot()
    effective_source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = (
        source_warehouse_columns or {}
    )
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    functions_by_key: dict[CompiledObjectKey, CompiledFunction] = {
        function.key: function for function in project.functions
    }
    function_locations: dict[str, CompiledRelationLocation] = build_function_locations(
        project.functions
    )
    scenario_model_names: frozenset[str] = frozenset(graph_plan.model_names)
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_upstream_deps(
        project
    )
    ordered_model_keys: tuple[CompiledObjectKey, ...] = tuple(
        key
        for key in topologically_order_keys(upstream_deps)
        if key.resource_type == CompiledResourceType.MODEL and key.name in scenario_model_names
    )
    fixture_plans: tuple[ScenarioFixturePlan, ...] = build_scenario_fixture_plans(
        scenario=scenario,
        graph_plan=graph_plan,
        relation_plan=relation_plan,
        sql_analysis_enabled=sql_analysis_enabled,
        sql_analysis_dialect=sql_analysis_dialect,
    )
    seed_entries: tuple[SeedPlanEntry, ...] = build_scenario_seed_entries(
        project=project,
        graph_plan=graph_plan,
        relation_plan=relation_plan,
    )
    function_entries: tuple[FunctionPlanEntry, ...] = tuple(
        _build_scenario_function_entry(
            function=functions_by_key[key],
            adapter=adapter,
            relation_plan=relation_plan,
            function_locations=function_locations,
            source_warehouse_columns=effective_source_warehouse_columns,
        )
        for key in topologically_order_keys(upstream_deps)
        if key in graph_plan.function_deps and key in functions_by_key
    )

    model_entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    key: CompiledObjectKey
    for key in ordered_model_keys:
        model: CompiledModel = models_by_name[key.name]
        scenario_target: CompiledRelationLocation = _required_target(
            relation_plan.model_locations,
            model.name,
            kind=ScenarioArtifactKind.MODEL,
        )
        scenario_query_sql: str = _resolve_model_dbt_ref_fixtures(
            query_sql=model.query_sql,
            relation_plan=relation_plan,
        )
        entry: ModelPlanEntry
        model_warnings: tuple[PlanWarning, ...]
        entry, model_warnings = plan_model(
            model=replace(model, destination=scenario_target, query_sql=scenario_query_sql),
            snapshot=effective_snapshot,
            adapter=adapter,
            model_locations=relation_plan.model_locations,
            models_by_name=models_by_name,
            seed_locations=relation_plan.seed_locations,
            function_locations=function_locations,
            source_map=relation_plan.source_map,
            source_warehouse_columns=effective_source_warehouse_columns,
            star_exclude_keyword=adapter.star_exclude_keyword(),
            sql_analysis_enabled=sql_analysis_enabled,
            query_change_tracking=False,
            full_refresh=True,
            start_cursor_override=None,
            end_cursor_override=None,
        )
        model_entries.append(entry)
        warnings.extend(model_warnings)

    expected_expectations: tuple[ScenarioExpectedExpectationPlan, ...] = tuple(
        _build_expected_check_plan(
            expected_cte=expected_cte,
            relation_plan=relation_plan,
            sql_analysis_enabled=sql_analysis_enabled,
            sql_analysis_dialect=sql_analysis_dialect,
        )
        for expected_cte in scenario.expected_ctes
    )
    assertion_expectations: tuple[ScenarioAssertionExpectationPlan, ...] = tuple(
        ScenarioAssertionExpectationPlan(
            name=assertion_cte.name.removeprefix("__assert__"),
            sql=resolve_scenario_check_sql(
                sql=assertion_cte.sql_body,
                relation_plan=relation_plan,
                sql_analysis_enabled=sql_analysis_enabled,
                sql_analysis_dialect=sql_analysis_dialect,
            ),
        )
        for assertion_cte in scenario.assertion_ctes
    )

    return (
        ScenarioExecutionPlan(
            key=scenario.key,
            name=scenario.name,
            graph_plan=graph_plan,
            relation_plan=relation_plan,
            fixture_plans=fixture_plans,
            seed_entries=seed_entries,
            function_entries=function_entries,
            model_entries=tuple(model_entries),
            hook_functions=project.hook_functions,
            expected_expectations=expected_expectations,
            assertion_expectations=assertion_expectations,
        ),
        tuple(warnings),
    )


def _build_scenario_function_entry(
    *,
    function: CompiledFunction,
    adapter: BaseAdapter,
    relation_plan: ScenarioRelationPlan,
    function_locations: dict[str, CompiledRelationLocation],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
) -> FunctionPlanEntry:
    return FunctionPlanEntry(
        key=function.key,
        name=function.name,
        relative_path=function.relative_path,
        destination=function.destination,
        arguments=function.arguments,
        returns=function.returns,
        body_sql=resolve_function_sql(
            adapter=adapter,
            function=function,
            model_locations=relation_plan.model_locations,
            seed_locations=relation_plan.seed_locations,
            function_locations=function_locations,
            source_map=relation_plan.source_map,
            source_warehouse_columns=source_warehouse_columns,
            star_exclude_keyword=adapter.star_exclude_keyword(),
        ),
        fingerprint_query_sql=build_compiled_function_fingerprint_sql(function),
        fingerprint_destination=function.fingerprint_destination,
        return_columns=function.return_columns,
        language=function.language,
        source_file_path=function.source_file_path,
        runtime_version=function.runtime_version,
        entry_point=function.entry_point,
        packages=function.packages,
    )


def build_scenario_fixture_plans(
    *,
    scenario: CompiledSqlScenario,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
    sql_analysis_enabled: bool = True,
    sql_analysis_dialect: str | None = None,
) -> tuple[ScenarioFixturePlan, ...]:
    """Build self-contained fixture SQL plans, including shared helper CTEs."""

    helper_ctes: tuple[CompileSqlScenarioCte, ...] = _extract_helper_ctes(scenario)
    resolved_helper_ctes: tuple[CompileSqlScenarioCte, ...] = tuple(
        replace(
            helper_cte,
            sql_body=_resolve_project_source_refs(
                sql=helper_cte.sql_body,
                source_map=relation_plan.project_source_map,
                sql_analysis_enabled=sql_analysis_enabled,
                sql_analysis_dialect=sql_analysis_dialect,
            ),
        )
        for helper_cte in helper_ctes
    )
    source_ctes: dict[str, str] = _extract_fixture_ctes(
        scenario=scenario,
        prefix=SOURCE_TEST_CTE_PREFIX,
    )
    ref_ctes: dict[str, str] = _extract_fixture_ctes(
        scenario=scenario,
        prefix=REF_TEST_CTE_PREFIX,
    )
    seed_ctes: dict[str, str] = _extract_fixture_ctes(
        scenario=scenario,
        prefix=SEED_TEST_CTE_PREFIX,
    )
    dbt_ref_ctes: dict[str, str] = _extract_fixture_ctes(
        scenario=scenario,
        prefix=DBT_REF_TEST_CTE_PREFIX,
    )

    plans: list[ScenarioFixturePlan] = []
    source_name: str
    for source_name in graph_plan.source_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SOURCE,
                logical_name=source_name,
                destination=_required_target(
                    relation_plan.source_fixture_locations,
                    source_name,
                    kind=ScenarioArtifactKind.SOURCE,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(source_ctes, source_name, kind="source"),
                        source_map=relation_plan.project_source_map,
                        sql_analysis_enabled=sql_analysis_enabled,
                        sql_analysis_dialect=sql_analysis_dialect,
                    ),
                    helper_ctes=resolved_helper_ctes,
                ),
            )
        )

    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.REF,
                logical_name=ref_name,
                destination=_required_target(
                    relation_plan.ref_fixture_locations,
                    ref_name,
                    kind=ScenarioArtifactKind.REF,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(ref_ctes, ref_name, kind="ref"),
                        source_map=relation_plan.project_source_map,
                        sql_analysis_enabled=sql_analysis_enabled,
                        sql_analysis_dialect=sql_analysis_dialect,
                    ),
                    helper_ctes=resolved_helper_ctes,
                ),
            )
        )

    seed_name: str
    for seed_name in graph_plan.seed_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SEED,
                logical_name=seed_name,
                destination=_required_target(
                    relation_plan.seed_fixture_locations,
                    seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(seed_ctes, seed_name, kind="seed"),
                        source_map=relation_plan.project_source_map,
                        sql_analysis_enabled=sql_analysis_enabled,
                        sql_analysis_dialect=sql_analysis_dialect,
                    ),
                    helper_ctes=resolved_helper_ctes,
                ),
            )
        )

    dbt_ref_name: str
    for dbt_ref_name in graph_plan.dbt_ref_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.DBT_REF,
                logical_name=dbt_ref_name,
                destination=_required_target(
                    relation_plan.dbt_ref_fixture_locations,
                    dbt_ref_name,
                    kind=ScenarioArtifactKind.DBT_REF,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(dbt_ref_ctes, dbt_ref_name, kind="dbt_ref"),
                        source_map=relation_plan.project_source_map,
                        sql_analysis_enabled=sql_analysis_enabled,
                        sql_analysis_dialect=sql_analysis_dialect,
                    ),
                    helper_ctes=resolved_helper_ctes,
                ),
            )
        )

    return tuple(plans)


def build_scenario_seed_entries(
    *,
    project: CompiledProject,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
) -> tuple[SeedPlanEntry, ...]:
    """Build project seed load entries for required seeds not overridden by fixtures."""

    seeds_by_name: dict[str, CompiledSeed] = {seed.name: seed for seed in project.seeds}
    seed_fixture_names: frozenset[str] = frozenset(graph_plan.seed_fixture_names)
    seed_entries: list[SeedPlanEntry] = []
    seed_name: str
    for seed_name in graph_plan.seed_names:
        if seed_name in seed_fixture_names:
            continue
        seed: CompiledSeed | None = seeds_by_name.get(seed_name)
        if seed is None:
            raise PlannerInputError(
                f"Scenario '{graph_plan.name}' requires unknown seed '{seed_name}'",
                code=SCENARIO_PLAN_UNKNOWN_SEED,
            )
        seed_entries.append(
            SeedPlanEntry(
                key=seed.key,
                name=seed.name,
                destination=_required_target(
                    relation_plan.seed_locations,
                    seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                file_path=seed.seed_file.file_path,
                columns=extract_seed_columns(seed),
                csv_settings=seed.schema_entry.csv_settings,
            )
        )
    return tuple(seed_entries)


def _resolve_scenario_check_sql_with_sql_analysis(
    *, sql: str, relation_plan: ScenarioRelationPlan, sql_analysis_dialect: str | None
) -> str:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        raise PlannerInputError(
            "Scenario Polyglot resolution is enabled but Polyglot SQL is unavailable",
            code=SCENARIO_PLAN_SQLGLOT_UNAVAILABLE,
            help="Install SQLBuild with Polyglot SQL or run with SQL validation disabled.",
        )
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect=sql_analysis_dialect or "generic")
    except Exception as error:
        raise PlannerInputError(
            f"Scenario SQL could not be parsed with Polyglot: {error}",
            code=SCENARIO_PLAN_SQLGLOT_PARSE,
        ) from None

    parsed_dict: dict[str, Any] = parsed.to_dict()
    replacement_result: bool = _replace_relation_markers_in_polyglot_dict(
        parsed_dict,
        polyglot_module=polyglot_module,
        sql_analysis_dialect=sql_analysis_dialect,
        target_for_marker=lambda function_name, referenced_name: _scenario_target_name_for_marker(
            function_name=function_name,
            referenced_name=referenced_name,
            relation_plan=relation_plan,
        ),
    )
    if not replacement_result:
        return sql
    generated: list[str] = polyglot_module.generate(
        parsed_dict,
        dialect=sql_analysis_dialect or "generic",
    )
    if len(generated) != 1:
        return sql
    return generated[0]


def _build_expected_check_plan(
    *,
    expected_cte: CompileSqlScenarioCte,
    relation_plan: ScenarioRelationPlan,
    sql_analysis_enabled: bool,
    sql_analysis_dialect: str | None,
) -> ScenarioExpectedExpectationPlan:
    model_name: str = expected_cte.name.removeprefix("__expected__")
    actual_destination: CompiledRelationLocation = _required_target(
        relation_plan.model_locations,
        model_name,
        kind=ScenarioArtifactKind.MODEL,
    )
    return ScenarioExpectedExpectationPlan(
        model_name=model_name,
        actual_destination=actual_destination,
        expected_sql=resolve_scenario_check_sql(
            sql=expected_cte.sql_body,
            relation_plan=relation_plan,
            sql_analysis_enabled=sql_analysis_enabled,
            sql_analysis_dialect=sql_analysis_dialect,
        ),
    )


def _extract_helper_ctes(scenario: CompiledSqlScenario) -> tuple[CompileSqlScenarioCte, ...]:
    helpers: list[CompileSqlScenarioCte] = []
    cte: CompileSqlScenarioCte
    for cte in scenario.authored_ctes:
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(DBT_REF_TEST_CTE_PREFIX):
            continue
        helpers.append(cte)
    return tuple(helpers)


def _extract_fixture_ctes(*, scenario: CompiledSqlScenario, prefix: str) -> dict[str, str]:
    result: dict[str, str] = {}
    cte: CompileSqlScenarioCte
    for cte in scenario.authored_ctes:
        if cte.name.startswith(prefix):
            result[cte.name.removeprefix(prefix)] = cte.sql_body
    return result


def _wrap_sql_with_helpers(*, sql: str, helper_ctes: tuple[CompileSqlScenarioCte, ...]) -> str:
    if not helper_ctes:
        return sql
    helper_parts: list[str] = []
    helper_cte: CompileSqlScenarioCte
    for helper_cte in helper_ctes:
        helper_parts.append(f"{helper_cte.name} AS ({helper_cte.sql_body})")
    return f"WITH {', '.join(helper_parts)} {sql}"


def _resolve_project_source_refs(
    *,
    sql: str,
    source_map: dict[str, SourceEntry],
    sql_analysis_enabled: bool,
    sql_analysis_dialect: str | None,
) -> str:
    if sql_analysis_enabled:
        sql_analysis_result: str | None = _try_resolve_project_source_refs_with_sql_analysis(
            sql=sql,
            source_map=source_map,
            sql_analysis_dialect=sql_analysis_dialect,
        )
        if sql_analysis_result is not None:
            return sql_analysis_result

    def _replace_source(match: re.Match[str]) -> str:
        source: SourceEntry | None = source_map.get(match.group("name"))
        if source is None:
            return match.group(0)
        return render_source_relation(source)

    return _SOURCE_PATTERN.sub(_replace_source, sql)


def _try_resolve_project_source_refs_with_sql_analysis(
    *, sql: str, source_map: dict[str, SourceEntry], sql_analysis_dialect: str | None
) -> str | None:
    if SqlReferenceKind.SOURCE.function_name not in sql.lower():
        return None
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect=sql_analysis_dialect or "generic")
    except Exception as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "scenario source ref resolution parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    parsed_dict: dict[str, Any] = parsed.to_dict()
    expression_source_names: set[str] = set()

    def _target_for_source(function_name: str, referenced_name: str) -> str | None:
        if function_name != SqlReferenceKind.SOURCE.function_name:
            return None
        source: SourceEntry | None = source_map.get(referenced_name)
        if source is None:
            return None
        if source.expression is not None:
            expression_source_names.add(referenced_name)
            return None
        return render_source_relation(source)

    replacement_result: bool = _replace_relation_markers_in_polyglot_dict(
        parsed_dict,
        polyglot_module=polyglot_module,
        sql_analysis_dialect=sql_analysis_dialect,
        target_for_marker=_target_for_source,
    )
    if expression_source_names or not replacement_result:
        return None
    generated: list[str] = polyglot_module.generate(
        parsed_dict,
        dialect=sql_analysis_dialect or "generic",
    )
    if len(generated) != 1:
        return None
    return generated[0]


def _replace_relation_markers_in_polyglot_dict(
    node: Any,
    *,
    polyglot_module: Any,
    sql_analysis_dialect: str | None,
    target_for_marker: Any,
) -> bool:
    changed: bool = False
    if isinstance(node, dict):
        from_clause: Any | None = node.get("from")
        if isinstance(from_clause, dict):
            expressions: Any = from_clause.get("expressions")
            if isinstance(expressions, list):
                for index, expression in enumerate(expressions):
                    replacement: dict[str, Any] | None = _replacement_relation_expression(
                        expression,
                        polyglot_module=polyglot_module,
                        sql_analysis_dialect=sql_analysis_dialect,
                        target_for_marker=target_for_marker,
                    )
                    if replacement is not None:
                        expressions[index] = replacement
                        changed = True
        joins: Any | None = node.get("joins")
        if isinstance(joins, list):
            join: Any
            for join in joins:
                if not isinstance(join, dict):
                    continue
                replacement = _replacement_relation_expression(
                    join.get("this"),
                    polyglot_module=polyglot_module,
                    sql_analysis_dialect=sql_analysis_dialect,
                    target_for_marker=target_for_marker,
                )
                if replacement is not None:
                    join["this"] = replacement
                    changed = True
        value: Any
        for value in node.values():
            if isinstance(value, dict | list):
                changed = (
                    _replace_relation_markers_in_polyglot_dict(
                        value,
                        polyglot_module=polyglot_module,
                        sql_analysis_dialect=sql_analysis_dialect,
                        target_for_marker=target_for_marker,
                    )
                    or changed
                )
    elif isinstance(node, list):
        item: Any
        for item in node:
            if isinstance(item, dict | list):
                changed = (
                    _replace_relation_markers_in_polyglot_dict(
                        item,
                        polyglot_module=polyglot_module,
                        sql_analysis_dialect=sql_analysis_dialect,
                        target_for_marker=target_for_marker,
                    )
                    or changed
                )
    return changed


def _replacement_relation_expression(
    expression: Any,
    *,
    polyglot_module: Any,
    sql_analysis_dialect: str | None,
    target_for_marker: Any,
) -> dict[str, Any] | None:
    if not isinstance(expression, dict):
        return None
    alias_payload: Any | None = expression.get("alias")
    if isinstance(alias_payload, dict) and "this" in alias_payload:
        inner_replacement: dict[str, Any] | None = _replacement_relation_expression(
            alias_payload.get("this"),
            polyglot_module=polyglot_module,
            sql_analysis_dialect=sql_analysis_dialect,
            target_for_marker=target_for_marker,
        )
        if inner_replacement is None:
            return None
        alias_payload["this"] = inner_replacement
        return expression

    function_payload: Any | None = expression.get("function")
    if not isinstance(function_payload, dict):
        return None
    function_name: str = str(function_payload.get("name", "")).lower()
    referenced_name: str | None = _polyglot_marker_reference_name(
        function_name=function_name,
        function_payload=function_payload,
    )
    if referenced_name is None:
        return None
    target_name: str | None = target_for_marker(function_name, referenced_name)
    if target_name is None:
        return None
    return _polyglot_relation_dict(
        target_name=target_name,
        polyglot_module=polyglot_module,
        sql_analysis_dialect=sql_analysis_dialect,
    )


def _polyglot_marker_reference_name(
    *, function_name: str, function_payload: dict[str, Any]
) -> str | None:
    args: Any = function_payload.get("args")
    if not isinstance(args, list):
        return None
    if function_name == SqlReferenceKind.DBT_REF.function_name:
        if len(args) == 1:
            return _polyglot_column_arg_name(args[0])
        if len(args) == 2:
            first: str | None = _polyglot_column_arg_name(args[0])
            second: str | None = _polyglot_column_arg_name(args[1])
            if first is None or second is None:
                return None
            return f"{first}__{second}"
        return None
    if len(args) != 1:
        return None
    return _polyglot_column_arg_name(args[0])


def _polyglot_column_arg_name(argument: Any) -> str | None:
    if not isinstance(argument, dict):
        return None
    column_payload: Any | None = argument.get("column")
    if not isinstance(column_payload, dict):
        return None
    name_payload: Any | None = column_payload.get("name")
    if isinstance(name_payload, dict):
        raw_name: Any | None = name_payload.get("name")
        return str(raw_name) if raw_name is not None else None
    return str(name_payload) if name_payload is not None else None


def _polyglot_relation_dict(
    *, target_name: str, polyglot_module: Any, sql_analysis_dialect: str | None
) -> dict[str, Any] | None:
    try:
        parsed: Any = polyglot_module.parse_one(
            f"SELECT * FROM {target_name}",
            dialect=sql_analysis_dialect or "generic",
        )
    except Exception as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "scenario relation dict parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    parsed_dict: dict[str, Any] = parsed.to_dict()
    select_payload: Any | None = parsed_dict.get("select")
    if not isinstance(select_payload, dict):
        return None
    from_payload: Any | None = select_payload.get("from")
    if not isinstance(from_payload, dict):
        return None
    expressions: Any | None = from_payload.get("expressions")
    if not isinstance(expressions, list) or len(expressions) != 1:
        return None
    relation: Any = expressions[0]
    return relation if isinstance(relation, dict) else None


def _required_fixture_sql(fixture_sql: dict[str, str], logical_name: str, *, kind: str) -> str:
    sql: str | None = fixture_sql.get(logical_name)
    if sql is None:
        raise PlannerInputError(
            f"Scenario is missing {kind} fixture SQL '{logical_name}'",
            code=SCENARIO_PLAN_MISSING_FIXTURE_SQL,
        )
    return sql


def _required_target(
    targets: dict[str, CompiledRelationLocation],
    name: str,
    *,
    kind: ScenarioArtifactKind,
) -> CompiledRelationLocation:
    target: CompiledRelationLocation | None = targets.get(name)
    if target is None:
        raise PlannerInputError(
            f"Scenario relation plan is missing {kind.value} target '{name}'",
            code=SCENARIO_PLAN_MISSING_RELATION_TARGET,
            help="This is likely a SQLBuild bug. Please file an issue with the scenario name.",
        )
    return target


def _scenario_target_name_for_marker(
    *, function_name: str, referenced_name: str, relation_plan: ScenarioRelationPlan
) -> str | None:
    if function_name == SqlReferenceKind.REF.function_name:
        target: CompiledRelationLocation | None = relation_plan.model_locations.get(referenced_name)
        return None if target is None else target.qualified_name
    if function_name == SqlReferenceKind.SEED.function_name:
        target = relation_plan.seed_locations.get(referenced_name)
        return None if target is None else target.qualified_name
    if function_name == SqlReferenceKind.SOURCE.function_name:
        source: SourceEntry | None = relation_plan.source_map.get(referenced_name)
        return None if source is None else render_source_relation(source)
    if function_name == SqlReferenceKind.DBT_REF.function_name:
        target = relation_plan.dbt_ref_fixture_locations.get(referenced_name)
        return None if target is None else target.qualified_name
    return None


def _resolve_model_dbt_ref_fixtures(*, query_sql: str, relation_plan: ScenarioRelationPlan) -> str:
    def _replace_dbt_ref(match: re.Match[str]) -> str:
        target: CompiledRelationLocation | None = relation_plan.dbt_ref_fixture_locations.get(
            _dbt_ref_fixture_name(match)
        )
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    return _DBT_REF_PATTERN.sub(_replace_dbt_ref, query_sql)


def _dbt_ref_fixture_name(match: re.Match[str]) -> str:
    first: str = match.group("first")
    second: str | None = match.group("second")
    if second is None:
        return first
    return f"{first}__{second}"


def _target_for_artifact(
    *,
    artifacts: dict[ScenarioArtifactIdentity, str],
    kind: ScenarioArtifactKind,
    logical_name: str,
    database: str | None,
    schema: str | None,
) -> CompiledRelationLocation:
    identity: ScenarioArtifactIdentity = ScenarioArtifactIdentity(
        kind=kind,
        logical_name=logical_name,
    )
    physical_name: str | None = artifacts.get(identity)
    if physical_name is None:
        raise PlannerInputError(
            f"Scenario relation map is missing {kind.value} artifact '{logical_name}'",
            code=SCENARIO_PLAN_INTERNAL,
            help="This is likely a SQLBuild bug. Please file an issue with the scenario name.",
        )
    qualified_name: str | None = _qualified_name(
        database=database,
        schema=schema,
        name=physical_name,
    )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=physical_name,
        qualified_name=qualified_name,
    )


def _qualified_name(*, database: str | None, schema: str | None, name: str) -> str:
    parts: list[str] = []
    if database is not None:
        parts.append(database)
    if schema is not None:
        parts.append(schema)
    parts.append(name)
    return ".".join(parts)
