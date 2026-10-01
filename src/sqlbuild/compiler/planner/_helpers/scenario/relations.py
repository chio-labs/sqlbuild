"""Scenario relation override planning helpers."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
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
from sqlbuild.compiler.planner._helpers.fixtures.completion import (
    build_relation_fixture_completion,
)
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_execution_upstream_deps,
    topologically_order_keys,
)
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner._helpers.output.plan_entry import extract_seed_columns, plan_model
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    build_function_locations,
    replace_executable_matches,
)
from sqlbuild.compiler.planner._helpers.resolve.resolve import resolve_function_sql
from sqlbuild.compiler.planner.constants import (
    SCENARIO_PLAN_INTERNAL,
    SCENARIO_PLAN_INVALID_FIXTURE,
    SCENARIO_PLAN_MISSING_FIXTURE_SQL,
    SCENARIO_PLAN_MISSING_RELATION_TARGET,
    SCENARIO_PLAN_UNKNOWN_SEED,
    SCENARIO_PLAN_UNRESOLVED_RELATION_MARKER,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    CursorOverridePair,
    FunctionPlanEntry,
    ModelPlanContext,
    ModelPlanEntry,
    PlanWarning,
    RelationFixtureCompletion,
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
from sqlbuild.compiler.planner.types import (
    FixtureKey,
    ScenarioArtifactKind,
)
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.main.render_source_relation import render_source_relation
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SourceEntry

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
    render_qualified_name: Callable[..., str | None],
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
            render_qualified_name=render_qualified_name,
        )

    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        target: CompiledRelationLocation = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.REF,
            logical_name=ref_name,
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
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
            render_qualified_name=render_qualified_name,
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
            render_qualified_name=render_qualified_name,
        )

    seed_name: str
    for seed_name in graph_plan.seed_names:
        target = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.SEED,
            logical_name=seed_name,
            database=database,
            schema=schema,
            render_qualified_name=render_qualified_name,
        )
        seed_locations[seed_name] = target

    for seed_name in graph_plan.seed_fixture_names:
        seed_fixture_locations[seed_name] = _required_target(
            targets=seed_locations,
            name=seed_name,
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
    adapter: BaseAdapter,
    source_label: str,
    source_lexical_syntax: SqlLexicalSyntax,
) -> str:
    """Resolve refs, seeds, and sources in authored scenario expected/assertion SQL."""

    def _ref_target(match: re.Match[str]) -> str | None:
        return _location_name(relation_plan.model_locations.get(match.group("name")))

    def _seed_target(match: re.Match[str]) -> str | None:
        return _location_name(relation_plan.seed_locations.get(match.group("name")))

    def _dbt_ref_target(match: re.Match[str]) -> str | None:
        return _location_name(
            relation_plan.dbt_ref_fixture_locations.get(_dbt_ref_fixture_name(match))
        )

    return _replace_relation_markers(
        sql=sql,
        resolvers=(
            (_REF_PATTERN, _ref_target),
            (_SEED_PATTERN, _seed_target),
            (
                _SOURCE_PATTERN,
                _source_resolver(source_map=relation_plan.source_map, adapter=adapter),
            ),
            (_DBT_REF_PATTERN, _dbt_ref_target),
        ),
        source_label=source_label,
        source_lexical_syntax=source_lexical_syntax,
    )


def _source_resolver(
    *, source_map: dict[str, SourceEntry], adapter: BaseAdapter
) -> Callable[[re.Match[str]], str | None]:
    def _source_target(match: re.Match[str]) -> str | None:
        source: SourceEntry | None = source_map.get(match.group("name"))
        return None if source is None else render_source_relation(entry=source, adapter=adapter)

    return _source_target


def _location_name(location: CompiledRelationLocation | None) -> str | None:
    return None if location is None else location.qualified_name


def _marker_replacer(
    *, resolve_target: Callable[[re.Match[str]], str | None], source_label: str
) -> Callable[[re.Match[str]], str]:
    def _replace(match: re.Match[str]) -> str:
        target: str | None = resolve_target(match)
        if target is None:
            raise PlannerInputError(
                f"Scenario SQL in {source_label} references {match.group(0)!r}, which is "
                "not a relation in this scenario",
                code=SCENARIO_PLAN_UNRESOLVED_RELATION_MARKER,
                help="Reference a model, seed, source, or dbt ref the scenario builds or "
                "provides as a fixture.",
            )
        return target

    return _replace


def _replace_relation_markers(
    *,
    sql: str,
    resolvers: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str | None]], ...],
    source_label: str,
    source_lexical_syntax: SqlLexicalSyntax,
) -> str:
    result: str = sql
    pattern: re.Pattern[str]
    resolve_target: Callable[[re.Match[str]], str | None]
    for pattern, resolve_target in resolvers:
        try:
            result = replace_executable_matches(
                sql=result,
                pattern=pattern,
                replace=_marker_replacer(resolve_target=resolve_target, source_label=source_label),
                lexical_syntax=source_lexical_syntax,
            )
        except CompileInputError as error:
            raise PlannerInputError(
                f"Scenario SQL in {source_label} could not be scanned for relation markers: "
                f"{error}",
                code=SCENARIO_PLAN_UNRESOLVED_RELATION_MARKER,
                help="Close every quoted string and block comment using the project dialect's "
                "quoting and comment rules.",
            ) from None
    return result


def build_scenario_execution_plan(
    *,
    scenario: CompiledSqlScenario,
    project: CompiledProject,
    adapter: BaseAdapter,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
    source_lexical_syntax: SqlLexicalSyntax,
    snapshot: WarehouseSnapshot | None = None,
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] | None = None,
    sql_analysis_enabled: bool = True,
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
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    ordered_model_keys: tuple[CompiledObjectKey, ...] = tuple(
        key
        for key in topologically_order_keys(upstream=upstream_deps)
        if key.resource_type == CompiledResourceType.MODEL and key.name in scenario_model_names
    )
    scenario_fixture_groups: tuple[tuple[CompiledResourceType, dict[str, str]], ...] = (
        (
            CompiledResourceType.SOURCE,
            _extract_fixture_ctes(scenario=scenario, prefix=SOURCE_TEST_CTE_PREFIX),
        ),
        (
            CompiledResourceType.MODEL,
            _extract_fixture_ctes(scenario=scenario, prefix=REF_TEST_CTE_PREFIX),
        ),
        (
            CompiledResourceType.SEED,
            _extract_fixture_ctes(scenario=scenario, prefix=SEED_TEST_CTE_PREFIX),
        ),
    )
    fixture_sql_overrides: dict[FixtureKey, str] | None = None
    if sql_analysis_enabled:
        fixture_completion: RelationFixtureCompletion = build_relation_fixture_completion(
            project=project,
            adapter=adapter,
            ordered_model_names=tuple(key.name for key in ordered_model_keys),
            fixture_groups=scenario_fixture_groups,
        )
        if fixture_completion.diagnostics:
            source_path: str = _scenario_source_label(scenario)
            details: str = "\n".join(
                f"- {diagnostic.message}" for diagnostic in fixture_completion.diagnostics
            )
            raise PlannerInputError(
                f"Scenario '{scenario.name}' has invalid relation fixtures in "
                f"{source_path}:\n{details}",
                code=SCENARIO_PLAN_INVALID_FIXTURE,
            )
        fixture_sql_overrides = fixture_completion.fixture_sql_by_key
    fixture_plans: tuple[ScenarioFixturePlan, ...] = build_scenario_fixture_plans(
        scenario=scenario,
        graph_plan=graph_plan,
        relation_plan=relation_plan,
        adapter=adapter,
        source_lexical_syntax=source_lexical_syntax,
        fixture_sql_overrides=fixture_sql_overrides,
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
        for key in topologically_order_keys(upstream=upstream_deps)
        if key in graph_plan.function_deps and key in functions_by_key
    )

    model_entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    key: CompiledObjectKey
    for key in ordered_model_keys:
        model: CompiledModel = models_by_name[key.name]
        scenario_target: CompiledRelationLocation = _required_target(
            targets=relation_plan.model_locations,
            name=model.name,
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
            context=ModelPlanContext(
                model_locations=relation_plan.model_locations,
                models_by_name=models_by_name,
                functions_by_name={function.name: function for function in project.functions},
                seed_locations=relation_plan.seed_locations,
                function_locations=function_locations,
                source_map=relation_plan.source_map,
                source_warehouse_columns=effective_source_warehouse_columns,
                star_exclude_keyword=adapter.star_exclude_keyword(),
            ),
            sql_analysis_enabled=sql_analysis_enabled,
            query_change_tracking=False,
            full_refresh=True,
            cursor_overrides=CursorOverridePair(),
        )
        model_entries.append(entry)
        warnings.extend(model_warnings)

    expected_expectations: tuple[ScenarioExpectedExpectationPlan, ...] = tuple(
        _build_expected_check_plan(
            expected_cte=expected_cte,
            relation_plan=relation_plan,
            adapter=adapter,
            source_label=_scenario_source_label(scenario),
            source_lexical_syntax=source_lexical_syntax,
        )
        for expected_cte in scenario.expected_ctes
    )
    assertion_expectations: tuple[ScenarioAssertionExpectationPlan, ...] = tuple(
        ScenarioAssertionExpectationPlan(
            name=assertion_cte.name.removeprefix("__assert__"),
            sql=resolve_scenario_check_sql(
                sql=assertion_cte.sql_body,
                relation_plan=relation_plan,
                adapter=adapter,
                source_label=_scenario_source_label(scenario),
                source_lexical_syntax=source_lexical_syntax,
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
    adapter: BaseAdapter,
    source_lexical_syntax: SqlLexicalSyntax,
    fixture_sql_overrides: dict[FixtureKey, str] | None = None,
) -> tuple[ScenarioFixturePlan, ...]:
    """Build self-contained fixture SQL plans, including shared helper CTEs."""

    source_label: str = _scenario_source_label(scenario)
    helper_ctes: tuple[CompileSqlScenarioCte, ...] = _extract_helper_ctes(scenario)
    resolved_helper_ctes: tuple[CompileSqlScenarioCte, ...] = tuple(
        replace(
            helper_cte,
            sql_body=_resolve_project_source_refs(
                sql=helper_cte.sql_body,
                source_map=relation_plan.project_source_map,
                adapter=adapter,
                source_label=source_label,
                source_lexical_syntax=source_lexical_syntax,
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
    overrides: dict[FixtureKey, str] = fixture_sql_overrides or {}
    source_ctes = _apply_fixture_overrides(
        resource_type=CompiledResourceType.SOURCE,
        fixture_sql=source_ctes,
        overrides=overrides,
    )
    ref_ctes = _apply_fixture_overrides(
        resource_type=CompiledResourceType.MODEL,
        fixture_sql=ref_ctes,
        overrides=overrides,
    )
    seed_ctes = _apply_fixture_overrides(
        resource_type=CompiledResourceType.SEED,
        fixture_sql=seed_ctes,
        overrides=overrides,
    )

    plans: list[ScenarioFixturePlan] = []
    source_name: str
    for source_name in graph_plan.source_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SOURCE,
                logical_name=source_name,
                destination=_required_target(
                    targets=relation_plan.source_fixture_locations,
                    name=source_name,
                    kind=ScenarioArtifactKind.SOURCE,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(
                            fixture_sql=source_ctes, logical_name=source_name, kind="source"
                        ),
                        source_map=relation_plan.project_source_map,
                        adapter=adapter,
                        source_label=source_label,
                        source_lexical_syntax=source_lexical_syntax,
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
                    targets=relation_plan.ref_fixture_locations,
                    name=ref_name,
                    kind=ScenarioArtifactKind.REF,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(
                            fixture_sql=ref_ctes, logical_name=ref_name, kind="ref"
                        ),
                        source_map=relation_plan.project_source_map,
                        adapter=adapter,
                        source_label=source_label,
                        source_lexical_syntax=source_lexical_syntax,
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
                    targets=relation_plan.seed_fixture_locations,
                    name=seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(
                            fixture_sql=seed_ctes, logical_name=seed_name, kind="seed"
                        ),
                        source_map=relation_plan.project_source_map,
                        adapter=adapter,
                        source_label=source_label,
                        source_lexical_syntax=source_lexical_syntax,
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
                    targets=relation_plan.dbt_ref_fixture_locations,
                    name=dbt_ref_name,
                    kind=ScenarioArtifactKind.DBT_REF,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_resolve_project_source_refs(
                        sql=_required_fixture_sql(
                            fixture_sql=dbt_ref_ctes,
                            logical_name=dbt_ref_name,
                            kind="dbt_ref",
                        ),
                        source_map=relation_plan.project_source_map,
                        adapter=adapter,
                        source_label=source_label,
                        source_lexical_syntax=source_lexical_syntax,
                    ),
                    helper_ctes=resolved_helper_ctes,
                ),
            )
        )

    return tuple(plans)


def _apply_fixture_overrides(
    *,
    resource_type: CompiledResourceType,
    fixture_sql: dict[str, str],
    overrides: dict[FixtureKey, str],
) -> dict[str, str]:
    return {name: overrides.get((resource_type, name), sql) for name, sql in fixture_sql.items()}


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
                    targets=relation_plan.seed_locations,
                    name=seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                file_path=seed.seed_file.file_path,
                columns=extract_seed_columns(seed),
                csv_settings=seed.schema_entry.csv_settings,
            )
        )
    return tuple(seed_entries)


def _build_expected_check_plan(
    *,
    expected_cte: CompileSqlScenarioCte,
    relation_plan: ScenarioRelationPlan,
    adapter: BaseAdapter,
    source_label: str,
    source_lexical_syntax: SqlLexicalSyntax,
) -> ScenarioExpectedExpectationPlan:
    model_name: str = expected_cte.name.removeprefix("__expected__")
    actual_destination: CompiledRelationLocation = _required_target(
        targets=relation_plan.model_locations,
        name=model_name,
        kind=ScenarioArtifactKind.MODEL,
    )
    return ScenarioExpectedExpectationPlan(
        model_name=model_name,
        actual_destination=actual_destination,
        expected_sql=resolve_scenario_check_sql(
            sql=expected_cte.sql_body,
            relation_plan=relation_plan,
            adapter=adapter,
            source_label=source_label,
            source_lexical_syntax=source_lexical_syntax,
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
    adapter: BaseAdapter,
    source_label: str,
    source_lexical_syntax: SqlLexicalSyntax,
) -> str:
    return _replace_relation_markers(
        sql=sql,
        resolvers=((_SOURCE_PATTERN, _source_resolver(source_map=source_map, adapter=adapter)),),
        source_label=source_label,
        source_lexical_syntax=source_lexical_syntax,
    )


def _scenario_source_label(scenario: CompiledSqlScenario) -> str:
    return str(scenario.source_path or scenario.name)


def _required_fixture_sql(*, fixture_sql: dict[str, str], logical_name: str, kind: str) -> str:
    sql: str | None = fixture_sql.get(logical_name)
    if sql is None:
        raise PlannerInputError(
            f"Scenario is missing {kind} fixture SQL '{logical_name}'",
            code=SCENARIO_PLAN_MISSING_FIXTURE_SQL,
        )
    return sql


def _required_target(
    *,
    targets: dict[str, CompiledRelationLocation],
    name: str,
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
    render_qualified_name: Callable[..., str | None],
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
    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=physical_name,
    )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=physical_name,
        qualified_name=qualified_name if qualified_name is not None else physical_name,
    )
