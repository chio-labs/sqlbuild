"""Graph inference and validation for SQL-native scenarios."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlScenario,
    CompileSqlScenarioCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.constants import (
    SCENARIO_PLAN_GRAPH_VALIDATION,
    SCENARIO_PLAN_SQLGLOT_PARSE,
    SCENARIO_PLAN_SQLGLOT_UNAVAILABLE,
)
from sqlbuild.compiler.planner.models import PlanWarning, ScenarioGraphPlan
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_REF_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.REF)}\s*"
    r"[\"']?(?P<name>[A-Za-z_][A-Za-z0-9_.]*)[\"']?\s*\)"
)


@dataclass(frozen=True)
class _UpstreamRequirements:
    """Upstream closure requirements collected for one scenario."""

    model_names: frozenset[str]
    required_ref_fixture_names: frozenset[str]
    required_source_names: frozenset[str]
    required_seed_names: frozenset[str]
    required_dbt_ref_fixture_names: frozenset[str]
    function_deps: tuple[CompiledObjectKey, ...]
    warnings: tuple[PlanWarning, ...]


def plan_scenario_graph(
    *,
    scenario: CompiledSqlScenario,
    project: CompiledProject,
    sql_analysis_enabled: bool = True,
    sql_analysis_dialect: str | None = None,
) -> tuple[ScenarioGraphPlan, tuple[PlanWarning, ...]]:
    """Infer scenario target models, build closure, and required fixtures."""

    model_map: dict[str, CompiledModel] = {model.name: model for model in project.models}
    source_names: frozenset[str] = frozenset(source.name for source in project.sources)
    seed_names: frozenset[str] = frozenset(seed.name for seed in project.seeds)
    assertion_target_names, assertion_warnings = _extract_assertion_target_names(
        assertion_ctes=scenario.assertion_ctes,
        scenario_name=scenario.name,
        sql_analysis_enabled=sql_analysis_enabled,
        sql_analysis_dialect=sql_analysis_dialect,
    )
    target_model_names: tuple[str, ...] = _dedupe_names(
        (*scenario.expected_model_names, *assertion_target_names)
    )

    warnings: list[PlanWarning] = []
    warnings.extend(assertion_warnings)
    warnings.extend(
        _declared_name_warnings(
            scenario=scenario,
            target_model_names=target_model_names,
            assertion_target_names=assertion_target_names,
            model_map=model_map,
            source_names=source_names,
            seed_names=seed_names,
        )
    )

    ref_fixture_names: frozenset[str] = frozenset(scenario.ref_fixture_names)
    source_fixture_names: frozenset[str] = frozenset(scenario.source_fixture_names)
    seed_fixture_names: frozenset[str] = frozenset(scenario.seed_fixture_names)
    dbt_ref_fixture_names: frozenset[str] = frozenset(scenario.dbt_ref_fixture_names)

    requirements: _UpstreamRequirements = _collect_upstream_requirements(
        target_model_names=target_model_names,
        scenario_name=scenario.name,
        model_map=model_map,
        ref_fixture_names=ref_fixture_names,
    )
    warnings.extend(requirements.warnings)
    model_names: frozenset[str] = requirements.model_names
    required_ref_fixture_names: frozenset[str] = requirements.required_ref_fixture_names
    required_source_names: frozenset[str] = requirements.required_source_names
    required_seed_names: frozenset[str] = requirements.required_seed_names
    required_dbt_ref_fixture_names: frozenset[str] = requirements.required_dbt_ref_fixture_names
    function_deps: tuple[CompiledObjectKey, ...] = requirements.function_deps

    missing_source_names: tuple[str, ...] = tuple(
        sorted(required_source_names - source_fixture_names)
    )
    source_name: str
    for source_name in missing_source_names:
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.ERROR,
                message=(
                    f"Scenario '{scenario.name}' requires source '{source_name}', "
                    "but no fixture was provided. Add a CTE named "
                    f"__source__{_fixture_name_for(source_name)} AS (...)."
                ),
            )
        )

    dbt_ref_fixture_name: str
    for dbt_ref_fixture_name in sorted(required_dbt_ref_fixture_names - dbt_ref_fixture_names):
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.ERROR,
                message=(
                    f"Scenario '{scenario.name}' requires dbt ref '{dbt_ref_fixture_name}', "
                    "but no fixture was provided. Add a CTE named "
                    f"__dbt_ref__{dbt_ref_fixture_name} AS (...)."
                ),
            )
        )

    plan: ScenarioGraphPlan = ScenarioGraphPlan(
        key=scenario.key,
        name=scenario.name,
        target_model_names=tuple(sorted(target_model_names)),
        assertion_target_model_names=tuple(sorted(assertion_target_names)),
        model_names=tuple(sorted(model_names)),
        source_fixture_names=tuple(sorted(required_source_names)),
        ref_fixture_names=tuple(sorted(required_ref_fixture_names)),
        seed_names=tuple(sorted(required_seed_names)),
        seed_fixture_names=tuple(sorted(required_seed_names & seed_fixture_names)),
        dbt_ref_fixture_names=tuple(sorted(required_dbt_ref_fixture_names)),
        function_deps=tuple(function_deps),
    )
    return plan, tuple(warnings)


def _extract_assertion_target_names(
    *,
    assertion_ctes: tuple[CompileSqlScenarioCte, ...],
    scenario_name: str,
    sql_analysis_enabled: bool,
    sql_analysis_dialect: str | None,
) -> tuple[tuple[str, ...], tuple[PlanWarning, ...]]:
    names: list[str] = []
    warnings: list[PlanWarning] = []
    cte: CompileSqlScenarioCte
    for cte in assertion_ctes:
        if sql_analysis_enabled:
            try:
                names.extend(
                    _extract_assertion_target_names_with_sql_analysis(
                        sql=cte.sql_body,
                        sql_analysis_dialect=sql_analysis_dialect,
                    )
                )
            except ValueError as error:
                warnings.append(
                    _error(
                        message=(
                            f"Scenario '{scenario_name}' assertion CTE '{cte.name}' could not be "
                            f"parsed with Polyglot: {error}"
                        ),
                        code=str(getattr(error, "code", SCENARIO_PLAN_SQLGLOT_PARSE)),
                    )
                )
            continue
        match: re.Match[str]
        for match in _REF_PATTERN.finditer(cte.sql_body):
            names.append(match.group("name"))
    return _dedupe_names(tuple(names)), tuple(warnings)


def _extract_assertion_target_names_with_sql_analysis(
    *, sql: str, sql_analysis_dialect: str | None
) -> tuple[str, ...]:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        error: ValueError = ValueError("Polyglot is enabled but unavailable")
        object.__setattr__(error, "code", SCENARIO_PLAN_SQLGLOT_UNAVAILABLE)
        raise error
    try:
        parsed: Any = (
            polyglot_module.parse_one(sql, dialect=sql_analysis_dialect)
            if sql_analysis_dialect is not None
            else polyglot_module.parse_one(sql, dialect="generic")
        )
    except Exception as error:
        value_error: ValueError = ValueError(str(error))
        object.__setattr__(value_error, "code", SCENARIO_PLAN_SQLGLOT_PARSE)
        raise value_error from None

    names: list[str] = []
    function: Any
    for function in parsed.find_all(polyglot_module.Function):
        function_name: str = str(function.name).lower()
        if function_name != SqlReferenceKind.REF.function_name:
            continue
        expressions: list[Any] = list(function.expressions)
        if len(expressions) != 1:
            continue
        argument: Any = expressions[0]
        if not hasattr(argument, "name"):
            continue
        names.append(str(argument.name))
    return tuple(names)


def _declared_name_warnings(
    *,
    scenario: CompiledSqlScenario,
    target_model_names: tuple[str, ...],
    assertion_target_names: tuple[str, ...],
    model_map: dict[str, CompiledModel],
    source_names: frozenset[str],
    seed_names: frozenset[str],
) -> tuple[PlanWarning, ...]:
    warnings: list[PlanWarning] = []
    expected_model_name: str
    for expected_model_name in scenario.expected_model_names:
        if expected_model_name not in model_map:
            warnings.append(
                _error(
                    message=(
                        f"Scenario '{scenario.name}' expects unknown model '{expected_model_name}'."
                    )
                )
            )

    assertion_target_name: str
    for assertion_target_name in assertion_target_names:
        if assertion_target_name not in model_map:
            warnings.append(
                _error(
                    message=f"Scenario '{scenario.name}' assertion references unknown model "
                    f"'{assertion_target_name}'."
                )
            )

    if not target_model_names:
        warnings.append(
            _error(
                message=f"Scenario '{scenario.name}' has no target models. Add __expected__<model> "
                "or reference a model with __ref(...) inside an __assert__ CTE."
            )
        )

    ref_fixture_name: str
    for ref_fixture_name in scenario.ref_fixture_names:
        if ref_fixture_name not in model_map:
            warnings.append(
                _error(
                    message=f"Scenario '{scenario.name}' provides fixture for unknown model "
                    f"'{ref_fixture_name}'."
                )
            )

    source_fixture_name: str
    for source_fixture_name in scenario.source_fixture_names:
        if source_fixture_name not in source_names:
            warnings.append(
                _error(
                    message=f"Scenario '{scenario.name}' provides fixture for unknown source "
                    f"'{source_fixture_name}'."
                )
            )

    seed_fixture_name: str
    for seed_fixture_name in scenario.seed_fixture_names:
        if seed_fixture_name not in seed_names:
            warnings.append(
                _error(
                    message=f"Scenario '{scenario.name}' provides fixture for unknown seed "
                    f"'{seed_fixture_name}'."
                )
            )
    return tuple(warnings)


def _collect_upstream_requirements(
    *,
    target_model_names: tuple[str, ...],
    scenario_name: str,
    model_map: dict[str, CompiledModel],
    ref_fixture_names: frozenset[str],
) -> _UpstreamRequirements:
    """Walk target model upstreams and collect required fixtures and functions."""

    def _walk(
        model_name: str,
        requirements: _UpstreamRequirements,
    ) -> _UpstreamRequirements:
        if model_name in ref_fixture_names:
            return _UpstreamRequirements(
                model_names=requirements.model_names,
                required_ref_fixture_names=requirements.required_ref_fixture_names | {model_name},
                required_source_names=requirements.required_source_names,
                required_seed_names=requirements.required_seed_names,
                required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                function_deps=requirements.function_deps,
                warnings=requirements.warnings,
            )
        if model_name in requirements.model_names:
            return requirements

        model: CompiledModel | None = model_map.get(model_name)
        if model is None:
            return requirements
        requirements = _UpstreamRequirements(
            model_names=requirements.model_names | {model_name},
            required_ref_fixture_names=requirements.required_ref_fixture_names,
            required_source_names=requirements.required_source_names,
            required_seed_names=requirements.required_seed_names,
            required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
            function_deps=requirements.function_deps,
            warnings=requirements.warnings,
        )

        dep_key: CompiledObjectKey
        for dep_key in model.deps:
            if dep_key.resource_type == CompiledResourceType.MODEL:
                if dep_key.name in ref_fixture_names:
                    requirements = _UpstreamRequirements(
                        model_names=requirements.model_names,
                        required_ref_fixture_names=requirements.required_ref_fixture_names
                        | {dep_key.name},
                        required_source_names=requirements.required_source_names,
                        required_seed_names=requirements.required_seed_names,
                        required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                        function_deps=requirements.function_deps,
                        warnings=requirements.warnings,
                    )
                    continue
                if dep_key.name not in model_map:
                    requirements = _UpstreamRequirements(
                        model_names=requirements.model_names,
                        required_ref_fixture_names=requirements.required_ref_fixture_names,
                        required_source_names=requirements.required_source_names,
                        required_seed_names=requirements.required_seed_names,
                        required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                        function_deps=requirements.function_deps,
                        warnings=(
                            *requirements.warnings,
                            _error(
                                message=(
                                    f"Scenario '{scenario_name}' requires model "
                                    f"'{dep_key.name}', "
                                    "but it does not exist and no __ref__ fixture was provided."
                                )
                            ),
                        ),
                    )
                    continue
                requirements = _walk(dep_key.name, requirements)
                continue
            if dep_key.resource_type == CompiledResourceType.SOURCE:
                requirements = _UpstreamRequirements(
                    model_names=requirements.model_names,
                    required_ref_fixture_names=requirements.required_ref_fixture_names,
                    required_source_names=requirements.required_source_names | {dep_key.name},
                    required_seed_names=requirements.required_seed_names,
                    required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                    function_deps=requirements.function_deps,
                    warnings=requirements.warnings,
                )
                continue
            if dep_key.resource_type == CompiledResourceType.SEED:
                requirements = _UpstreamRequirements(
                    model_names=requirements.model_names,
                    required_ref_fixture_names=requirements.required_ref_fixture_names,
                    required_source_names=requirements.required_source_names,
                    required_seed_names=requirements.required_seed_names | {dep_key.name},
                    required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                    function_deps=requirements.function_deps,
                    warnings=requirements.warnings,
                )
                continue
            if dep_key.resource_type == CompiledResourceType.DBT_REF:
                requirements = _UpstreamRequirements(
                    model_names=requirements.model_names,
                    required_ref_fixture_names=requirements.required_ref_fixture_names,
                    required_source_names=requirements.required_source_names,
                    required_seed_names=requirements.required_seed_names,
                    required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names
                    | {dep_key.name.replace(".", "__")},
                    function_deps=requirements.function_deps,
                    warnings=requirements.warnings,
                )
                continue
            if dep_key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
                if dep_key in requirements.function_deps:
                    continue
                requirements = _UpstreamRequirements(
                    model_names=requirements.model_names,
                    required_ref_fixture_names=requirements.required_ref_fixture_names,
                    required_source_names=requirements.required_source_names,
                    required_seed_names=requirements.required_seed_names,
                    required_dbt_ref_fixture_names=requirements.required_dbt_ref_fixture_names,
                    function_deps=(*requirements.function_deps, dep_key),
                    warnings=requirements.warnings,
                )
        return requirements

    requirements: _UpstreamRequirements = _UpstreamRequirements(
        model_names=frozenset(),
        required_ref_fixture_names=frozenset(),
        required_source_names=frozenset(),
        required_seed_names=frozenset(),
        required_dbt_ref_fixture_names=frozenset(),
        function_deps=(),
        warnings=(),
    )
    target_model_name: str
    for target_model_name in target_model_names:
        requirements = _walk(target_model_name, requirements)

    return requirements


def _dedupe_names(names: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    name: str
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return tuple(deduped)


def _fixture_name_for(name: str) -> str:
    return name.replace(".", "__")


def _error(*, message: str, code: str = SCENARIO_PLAN_GRAPH_VALIDATION) -> PlanWarning:
    return PlanWarning(
        model_name=None,
        severity=WarningSeverity.ERROR,
        message=message,
        code=code,
    )
