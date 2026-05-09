"""Scenario relation override planning helpers."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.constants import (
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSqlScenario,
    CompileSqlScenarioCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.graph import build_upstream_deps, topologically_order_keys
from sqlbuild.compiler.planner.helpers.plan_entry import extract_seed_columns, plan_model
from sqlbuild.compiler.planner.helpers.resolve.refs import build_function_targets
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanWarning,
    ScenarioArtifactIdentity,
    ScenarioAssertionCheckPlan,
    ScenarioExecutionPlan,
    ScenarioExpectedCheckPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
    SeedPlanEntry,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions
from sqlbuild.spec.models.source import SourceEntry

_REF_PATTERN: re.Pattern[str] = re.compile(
    r"__ref\(\s*[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)
_SEED_PATTERN: re.Pattern[str] = re.compile(
    r"__seed\(\s*[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)
_SOURCE_PATTERN: re.Pattern[str] = re.compile(
    r"__source\(\s*[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)


def build_scenario_relation_plan(
    *,
    project: CompiledProject,
    graph_plan: ScenarioGraphPlan,
    relation_map: ScenarioRelationMap,
    database: str | None = None,
    schema: str | None = None,
) -> ScenarioRelationPlan:
    """Build scenario-scoped relation targets and source entries."""

    artifacts: dict[ScenarioArtifactIdentity, str] = {
        artifact.identity: artifact.physical_name for artifact in relation_map.artifacts
    }
    source_entries: dict[str, SourceEntry] = {
        source.name: source.source_entry for source in project.sources
    }

    model_targets: dict[str, CompiledRelationTarget] = {}
    source_fixture_targets: dict[str, CompiledRelationTarget] = {}
    ref_fixture_targets: dict[str, CompiledRelationTarget] = {}
    seed_fixture_targets: dict[str, CompiledRelationTarget] = {}
    seed_targets: dict[str, CompiledRelationTarget] = {}
    source_map: dict[str, SourceEntry] = {}

    model_name: str
    for model_name in graph_plan.model_names:
        model_targets[model_name] = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.MODEL,
            logical_name=model_name,
            database=database,
            schema=schema,
        )

    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        target: CompiledRelationTarget = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.REF,
            logical_name=ref_name,
            database=database,
            schema=schema,
        )
        ref_fixture_targets[ref_name] = target
        model_targets[ref_name] = target

    source_name: str
    for source_name in graph_plan.source_fixture_names:
        target = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.SOURCE,
            logical_name=source_name,
            database=database,
            schema=schema,
        )
        source_fixture_targets[source_name] = target
        source_entry: SourceEntry = source_entries[source_name]
        source_map[source_name] = replace(
            source_entry,
            database=None,
            schema=None,
            table=None,
            expression=target.qualified_name or target.name,
            type_enforcement=False,
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
        seed_targets[seed_name] = target

    for seed_name in graph_plan.seed_fixture_names:
        seed_fixture_targets[seed_name] = _required_target(
            seed_targets,
            seed_name,
            kind=ScenarioArtifactKind.SEED,
        )

    return ScenarioRelationPlan(
        scenario_name=graph_plan.name,
        relation_map=relation_map,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        source_fixture_targets=source_fixture_targets,
        ref_fixture_targets=ref_fixture_targets,
        seed_fixture_targets=seed_fixture_targets,
    )


def resolve_scenario_check_sql(
    *,
    sql: str,
    relation_plan: ScenarioRelationPlan,
    sqlglot_enabled: bool = True,
    sqlglot_dialect: str | None = None,
) -> str:
    """Resolve refs, seeds, and sources in scenario expected/assertion SQL."""

    if sqlglot_enabled:
        return _resolve_scenario_check_sql_with_sqlglot(
            sql=sql,
            relation_plan=relation_plan,
            sqlglot_dialect=sqlglot_dialect,
        )

    def _replace_ref(match: re.Match[str]) -> str:
        target: CompiledRelationTarget | None = relation_plan.model_targets.get(match.group("name"))
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    def _replace_seed(match: re.Match[str]) -> str:
        target: CompiledRelationTarget | None = relation_plan.seed_targets.get(match.group("name"))
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    def _replace_source(match: re.Match[str]) -> str:
        source: SourceEntry | None = relation_plan.source_map.get(match.group("name"))
        if source is None or source.expression is None:
            return match.group(0)
        return source.expression

    result: str = _REF_PATTERN.sub(_replace_ref, sql)
    result = _SEED_PATTERN.sub(_replace_seed, result)
    return _SOURCE_PATTERN.sub(_replace_source, result)


def build_scenario_execution_plan(
    *,
    scenario: CompiledSqlScenario,
    project: CompiledProject,
    adapter: BaseAdapter,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
    snapshot: WarehouseSnapshot | None = None,
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] | None = None,
    sqlglot_enabled: bool = True,
    sqlglot_dialect: str | None = None,
) -> tuple[ScenarioExecutionPlan, tuple[PlanWarning, ...]]:
    """Build a dry-run execution plan for one SQL scenario."""

    effective_snapshot: WarehouseSnapshot = snapshot or WarehouseSnapshot()
    effective_source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = (
        source_warehouse_columns or {}
    )
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    function_targets: dict[str, CompiledRelationTarget] = build_function_targets(project.functions)
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
    )
    seed_entries: tuple[SeedPlanEntry, ...] = build_scenario_seed_entries(
        project=project,
        graph_plan=graph_plan,
        relation_plan=relation_plan,
    )

    model_entries: list[ModelPlanEntry] = []
    warnings: list[PlanWarning] = []
    key: CompiledObjectKey
    for key in ordered_model_keys:
        model: CompiledModel = models_by_name[key.name]
        scenario_target: CompiledRelationTarget = _required_target(
            relation_plan.model_targets,
            model.name,
            kind=ScenarioArtifactKind.MODEL,
        )
        entry: ModelPlanEntry
        model_warnings: tuple[PlanWarning, ...]
        entry, model_warnings = plan_model(
            model=replace(model, target=scenario_target),
            snapshot=effective_snapshot,
            adapter=adapter,
            model_targets=relation_plan.model_targets,
            models_by_name=models_by_name,
            seed_targets=relation_plan.seed_targets,
            function_targets=function_targets,
            source_map=relation_plan.source_map,
            source_warehouse_columns=effective_source_warehouse_columns,
            star_exclude_keyword=adapter.star_exclude_keyword(),
            sqlglot_enabled=sqlglot_enabled,
            query_change_tracking=False,
            full_refresh=True,
            start_cursor_override=None,
            end_cursor_override=None,
        )
        model_entries.append(entry)
        warnings.extend(model_warnings)

    expected_checks: tuple[ScenarioExpectedCheckPlan, ...] = tuple(
        _build_expected_check_plan(
            expected_cte=expected_cte,
            relation_plan=relation_plan,
            sqlglot_enabled=sqlglot_enabled,
            sqlglot_dialect=sqlglot_dialect,
        )
        for expected_cte in scenario.expected_ctes
    )
    assertion_checks: tuple[ScenarioAssertionCheckPlan, ...] = tuple(
        ScenarioAssertionCheckPlan(
            name=assertion_cte.name.removeprefix("__assert__"),
            sql=resolve_scenario_check_sql(
                sql=assertion_cte.sql_body,
                relation_plan=relation_plan,
                sqlglot_enabled=sqlglot_enabled,
                sqlglot_dialect=sqlglot_dialect,
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
            model_entries=tuple(model_entries),
            expected_checks=expected_checks,
            assertion_checks=assertion_checks,
        ),
        tuple(warnings),
    )


def build_scenario_fixture_plans(
    *,
    scenario: CompiledSqlScenario,
    graph_plan: ScenarioGraphPlan,
    relation_plan: ScenarioRelationPlan,
) -> tuple[ScenarioFixturePlan, ...]:
    """Build self-contained fixture SQL plans, including shared helper CTEs."""

    helper_ctes: tuple[CompileSqlScenarioCte, ...] = _extract_helper_ctes(scenario)
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

    plans: list[ScenarioFixturePlan] = []
    source_name: str
    for source_name in graph_plan.source_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SOURCE,
                logical_name=source_name,
                target=_required_target(
                    relation_plan.source_fixture_targets,
                    source_name,
                    kind=ScenarioArtifactKind.SOURCE,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_required_fixture_sql(source_ctes, source_name, kind="source"),
                    helper_ctes=helper_ctes,
                ),
            )
        )

    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.REF,
                logical_name=ref_name,
                target=_required_target(
                    relation_plan.ref_fixture_targets,
                    ref_name,
                    kind=ScenarioArtifactKind.REF,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_required_fixture_sql(ref_ctes, ref_name, kind="ref"),
                    helper_ctes=helper_ctes,
                ),
            )
        )

    seed_name: str
    for seed_name in graph_plan.seed_fixture_names:
        plans.append(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SEED,
                logical_name=seed_name,
                target=_required_target(
                    relation_plan.seed_fixture_targets,
                    seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                sql=_wrap_sql_with_helpers(
                    sql=_required_fixture_sql(seed_ctes, seed_name, kind="seed"),
                    helper_ctes=helper_ctes,
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
            raise ValueError(f"Scenario requires unknown seed '{seed_name}'")
        seed_entries.append(
            SeedPlanEntry(
                key=seed.key,
                name=seed.name,
                target=_required_target(
                    relation_plan.seed_targets,
                    seed_name,
                    kind=ScenarioArtifactKind.SEED,
                ),
                file_path=seed.seed_file.file_path,
                columns=extract_seed_columns(seed),
                csv_settings=seed.schema_entry.csv_settings,
            )
        )
    return tuple(seed_entries)


def _resolve_scenario_check_sql_with_sqlglot(
    *, sql: str, relation_plan: ScenarioRelationPlan, sqlglot_dialect: str | None
) -> str:
    sqlglot_module: Any | None = import_sqlglot()
    expressions_module: Any | None = import_sqlglot_expressions()
    if sqlglot_module is None or expressions_module is None:
        raise ValueError("SQLGlot is enabled but unavailable")
    try:
        parsed: Any = (
            sqlglot_module.parse_one(sql, read=sqlglot_dialect)
            if sqlglot_dialect is not None
            else sqlglot_module.parse_one(sql)
        )
    except Exception as error:
        raise ValueError(f"Scenario SQL could not be parsed with SQLGlot: {error}") from None

    table_type: type[Any] = expressions_module.Table
    anonymous_type: type[Any] = expressions_module.Anonymous

    def _replace_table(table: Any) -> Any:
        if not isinstance(table, table_type):
            return table
        anonymous: Any = table.this
        if not isinstance(anonymous, anonymous_type):
            return table
        function_name: str = str(anonymous.this).lower()
        expressions: list[Any] = list(anonymous.expressions)
        if len(expressions) != 1:
            return table
        argument: Any = expressions[0]
        if not hasattr(argument, "name"):
            return table
        referenced_name: str = str(argument.name)
        target_name: str | None = _scenario_target_name_for_marker(
            function_name=function_name,
            referenced_name=referenced_name,
            relation_plan=relation_plan,
        )
        if target_name is None:
            return table
        replacement: Any = expressions_module.to_table(target_name)
        alias: Any | None = table.args.get("alias")
        if alias is not None:
            replacement.set("alias", alias)
        return replacement

    return parsed.transform(_replace_table).sql(pretty=False)


def _build_expected_check_plan(
    *,
    expected_cte: CompileSqlScenarioCte,
    relation_plan: ScenarioRelationPlan,
    sqlglot_enabled: bool,
    sqlglot_dialect: str | None,
) -> ScenarioExpectedCheckPlan:
    model_name: str = expected_cte.name.removeprefix("__expected__")
    actual_target: CompiledRelationTarget = _required_target(
        relation_plan.model_targets,
        model_name,
        kind=ScenarioArtifactKind.MODEL,
    )
    return ScenarioExpectedCheckPlan(
        model_name=model_name,
        actual_target=actual_target,
        expected_sql=resolve_scenario_check_sql(
            sql=expected_cte.sql_body,
            relation_plan=relation_plan,
            sqlglot_enabled=sqlglot_enabled,
            sqlglot_dialect=sqlglot_dialect,
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


def _required_fixture_sql(fixture_sql: dict[str, str], logical_name: str, *, kind: str) -> str:
    sql: str | None = fixture_sql.get(logical_name)
    if sql is None:
        raise ValueError(f"Scenario is missing {kind} fixture SQL '{logical_name}'")
    return sql


def _required_target(
    targets: dict[str, CompiledRelationTarget],
    name: str,
    *,
    kind: ScenarioArtifactKind,
) -> CompiledRelationTarget:
    target: CompiledRelationTarget | None = targets.get(name)
    if target is None:
        raise ValueError(f"Scenario relation plan is missing {kind.value} target '{name}'")
    return target


def _scenario_target_name_for_marker(
    *, function_name: str, referenced_name: str, relation_plan: ScenarioRelationPlan
) -> str | None:
    if function_name == "__ref":
        target: CompiledRelationTarget | None = relation_plan.model_targets.get(referenced_name)
        return None if target is None else target.qualified_name
    if function_name == "__seed":
        target = relation_plan.seed_targets.get(referenced_name)
        return None if target is None else target.qualified_name
    if function_name == "__source":
        source: SourceEntry | None = relation_plan.source_map.get(referenced_name)
        return None if source is None else source.expression
    return None


def _target_for_artifact(
    *,
    artifacts: dict[ScenarioArtifactIdentity, str],
    kind: ScenarioArtifactKind,
    logical_name: str,
    database: str | None,
    schema: str | None,
) -> CompiledRelationTarget:
    identity: ScenarioArtifactIdentity = ScenarioArtifactIdentity(
        kind=kind,
        logical_name=logical_name,
    )
    physical_name: str | None = artifacts.get(identity)
    if physical_name is None:
        raise ValueError(f"Scenario relation map is missing {kind.value} artifact '{logical_name}'")
    qualified_name: str | None = _qualified_name(
        database=database,
        schema=schema,
        name=physical_name,
    )
    return CompiledRelationTarget(
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
