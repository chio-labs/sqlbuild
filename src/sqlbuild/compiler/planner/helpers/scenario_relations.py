"""Scenario relation override planning helpers."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationTarget,
)
from sqlbuild.compiler.planner.models import (
    ScenarioArtifactIdentity,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
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
    for seed_name in graph_plan.seed_fixture_names:
        target = _target_for_artifact(
            artifacts=artifacts,
            kind=ScenarioArtifactKind.SEED,
            logical_name=seed_name,
            database=database,
            schema=schema,
        )
        seed_fixture_targets[seed_name] = target
        seed_targets[seed_name] = target

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
