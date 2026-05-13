"""Test chain resolution for SQL-native unit tests."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.constants import (
    ASSERT_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.resolve.refs import resolve_udf_references
from sqlbuild.compiler.planner.helpers.sqlglot_sql_test_assembly import (
    try_resolve_test_model_sql_with_sqlglot,
)
from sqlbuild.compiler.planner.models import (
    ChainStep,
    PlanWarning,
    SqlglotResolvedTestSql,
    SqlTestAssertionStep,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import WarningSeverity

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')
_SEED_PATTERN: re.Pattern[str] = re.compile(r'__seed\("([^"]+)"\)')
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)"(?:,\s*"([^"]+)")?\)')


def plan_test(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    sqlglot_enabled: bool = False,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a test plan entry with chained resolution."""

    model_map: dict[str, CompiledModel] = {m.name: m for m in project.models}
    function_targets: dict[str, CompiledRelationTarget] = {
        function.name: function.target for function in project.functions
    }
    mock_refs: dict[str, str] = _extract_mock_refs(test)
    mock_sources: dict[str, str] = _extract_mock_sources(test)
    mock_seeds: dict[str, str] = _extract_mock_seeds(test)
    mock_dbt_refs: dict[str, str] = _extract_mock_dbt_refs(test)
    helper_ctes: tuple[CompileSqlTestCte, ...] = _extract_helper_ctes(test)
    expected_map: dict[str, str] = _extract_expected_ctes(test)
    assertion_map: dict[str, str] = _extract_assertion_ctes(test)
    assertion_target_names: tuple[str, ...] = _extract_assertion_ref_targets(
        assertion_map=assertion_map
    )

    expected_names: tuple[str, ...] = tuple(
        dict.fromkeys((*test.expected_model_names, *assertion_target_names))
    )
    ordered_names: tuple[str, ...] = _topo_sort_expected(
        expected_names=expected_names,
        model_map=model_map,
    )

    warnings: list[PlanWarning] = []
    reachable_mocks: set[str] = set()
    resolved: dict[str, str] = {}
    sqlglot_resolved: dict[str, SqlglotResolvedTestSql] = {}
    function_deps: list[CompiledObjectKey] = []

    chain_steps: list[ChainStep] = []
    model_name: str
    for model_name in ordered_names:
        model: CompiledModel | None = model_map.get(model_name)
        if model is None:
            warnings.append(
                PlanWarning(
                    model_name=None,
                    severity=WarningSeverity.ERROR,
                    message=(
                        f"test '{test.name}' expects model '{model_name}' which does not exist"
                    ),
                )
            )
            continue
        function_deps.extend(
            dep for dep in model.deps if dep.resource_type == CompiledResourceType.FUNCTION
        )

        query_sql: str = _resolve_test_model_query_sql(model=model, test=test)
        step_sql: str = _resolve_test_model_sql(
            query_sql=query_sql,
            mock_refs=mock_refs,
            mock_sources=mock_sources,
            mock_seeds=mock_seeds,
            mock_dbt_refs=mock_dbt_refs,
            helper_ctes=helper_ctes,
            resolved_chain=resolved,
            reachable_mocks=reachable_mocks,
            function_targets=function_targets,
        )
        resolved_value: str = f"({step_sql})"
        if sqlglot_enabled:
            sqlglot_sql: SqlglotResolvedTestSql | None = try_resolve_test_model_sql_with_sqlglot(
                query_sql=query_sql,
                mock_refs=mock_refs,
                mock_sources=mock_sources,
                mock_seeds=mock_seeds,
                mock_dbt_refs=mock_dbt_refs,
                function_targets={
                    name: target.qualified_name
                    for name, target in function_targets.items()
                    if target.qualified_name is not None
                },
                helper_ctes=helper_ctes,
                resolved_chain=sqlglot_resolved,
                reachable_mocks=reachable_mocks,
                file_label=str(test.test_file.relative_path),
            )
            if sqlglot_sql is not None:
                step_sql = sqlglot_sql.resolved_sql
                resolved_value = sqlglot_sql.resolved_sql
                sqlglot_resolved[model_name] = sqlglot_sql

        unresolved_warnings: tuple[PlanWarning, ...] = _validate_resolved_sql(
            resolved_sql=step_sql,
            test_name=test.name,
            model_name=model_name,
        )
        warnings.extend(unresolved_warnings)

        resolved[model_name] = resolved_value

        expected_cte_sql: str = expected_map.get(model_name, "")
        chain_steps.append(
            ChainStep(
                model_name=model_name,
                resolved_sql=step_sql,
                expected_cte_sql=expected_cte_sql or None,
            )
        )

    assertion_steps: list[SqlTestAssertionStep] = []
    assertion_name: str
    assertion_sql: str
    for assertion_name, assertion_sql in assertion_map.items():
        assertion_steps.append(
            SqlTestAssertionStep(
                name=assertion_name,
                resolved_sql=_resolve_assertion_sql(
                    sql=assertion_sql,
                    resolved_chain=resolved,
                    mock_refs=mock_refs,
                    mock_sources=mock_sources,
                    mock_seeds=mock_seeds,
                    mock_dbt_refs=mock_dbt_refs,
                    helper_ctes=helper_ctes,
                    function_targets=function_targets,
                ),
            )
        )

    unreachable_ref: str
    for unreachable_ref in sorted(set(mock_refs) - reachable_mocks):
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.WARNING,
                message=(
                    f"test '{test.name}' mock __ref__{unreachable_ref}"
                    f" is unreachable because a downstream model is"
                    f" also in the expected chain"
                ),
            )
        )

    unreachable_source: str
    for unreachable_source in sorted(set(mock_sources) - reachable_mocks):
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.WARNING,
                message=(f"test '{test.name}' mock __source__{unreachable_source} is unreachable"),
            )
        )

    unreachable_seed: str
    for unreachable_seed in sorted(set(mock_seeds) - reachable_mocks):
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.WARNING,
                message=(f"test '{test.name}' mock __seed__{unreachable_seed} is unreachable"),
            )
        )

    unreachable_dbt_ref: str
    for unreachable_dbt_ref in sorted(set(mock_dbt_refs) - reachable_mocks):
        warnings.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.WARNING,
                message=(
                    f"test '{test.name}' mock __dbt_ref__{unreachable_dbt_ref} is unreachable"
                ),
            )
        )

    entry: SqlTestPlanEntry = SqlTestPlanEntry(
        key=test.key,
        name=test.name,
        chain=tuple(chain_steps),
        assertions=tuple(assertion_steps),
        scope_deps=test.scope_deps,
        function_deps=_dedupe_function_deps(function_deps),
        sqlglot_enabled=sqlglot_enabled,
    )
    return entry, tuple(warnings)


def _extract_assertion_ref_targets(*, assertion_map: dict[str, str]) -> tuple[str, ...]:
    targets: list[str] = []
    sql: str
    for sql in assertion_map.values():
        match: re.Match[str]
        for match in _REF_PATTERN.finditer(sql):
            targets.append(match.group(1))
    return tuple(dict.fromkeys(targets))


def _resolve_assertion_sql(
    *,
    sql: str,
    resolved_chain: dict[str, str],
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    mock_dbt_refs: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    function_targets: dict[str, CompiledRelationTarget],
) -> str:
    reachable_mocks: set[str] = set()
    assertion_resolved_chain: dict[str, str] = {
        name: _wrap_resolved_chain_sql(sql) for name, sql in resolved_chain.items()
    }
    return _resolve_test_model_sql(
        query_sql=sql,
        mock_refs=mock_refs,
        mock_sources=mock_sources,
        mock_seeds=mock_seeds,
        mock_dbt_refs=mock_dbt_refs,
        helper_ctes=helper_ctes,
        resolved_chain=assertion_resolved_chain,
        reachable_mocks=reachable_mocks,
        function_targets=function_targets,
    )


def _wrap_resolved_chain_sql(sql: str) -> str:
    stripped: str = sql.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped
    return f"({stripped})"


def _dedupe_function_deps(deps: list[CompiledObjectKey]) -> tuple[CompiledObjectKey, ...]:
    deduped: list[CompiledObjectKey] = []
    seen: set[CompiledObjectKey] = set()
    dep: CompiledObjectKey
    for dep in deps:
        if dep in seen:
            continue
        seen.add(dep)
        deduped.append(dep)
    return tuple(deduped)


def _resolve_test_model_query_sql(
    *,
    model: CompiledModel,
    test: CompiledSqlTest,
) -> str:
    """Resolve model SQL for one SQL test, applying test macro mocks if present."""

    return test.model_query_overrides.get(model.name, model.query_sql)


def _resolve_test_model_sql(
    *,
    query_sql: str,
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    mock_dbt_refs: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    resolved_chain: dict[str, str],
    reachable_mocks: set[str],
    function_targets: dict[str, CompiledRelationTarget],
) -> str:
    """Replace refs and sources in model SQL with mocks or chain outputs."""

    helper_with: str = _build_helper_with_clause(helper_ctes)

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        if ref_name in resolved_chain:
            return resolved_chain[ref_name]
        if ref_name in mock_refs:
            reachable_mocks.add(ref_name)
            mock_body: str = mock_refs[ref_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    def _replace_source(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        if source_name in mock_sources:
            reachable_mocks.add(source_name)
            mock_body: str = mock_sources[source_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    def _replace_seed(match: re.Match[str]) -> str:
        seed_name: str = match.group(1)
        if seed_name in mock_seeds:
            reachable_mocks.add(seed_name)
            mock_body: str = mock_seeds[seed_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    def _replace_dbt_ref(match: re.Match[str]) -> str:
        dbt_ref_name: str = _dbt_ref_fixture_name(
            package_name=match.group(1), model_name=match.group(2)
        )
        if dbt_ref_name in mock_dbt_refs:
            reachable_mocks.add(dbt_ref_name)
            mock_body: str = mock_dbt_refs[dbt_ref_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    result: str = _REF_PATTERN.sub(_replace_ref, query_sql)
    result = _SOURCE_PATTERN.sub(_replace_source, result)
    result = _SEED_PATTERN.sub(_replace_seed, result)
    result = _DBT_REF_PATTERN.sub(_replace_dbt_ref, result)
    result = resolve_udf_references(query_sql=result, function_targets=function_targets)
    return result


def _validate_resolved_sql(
    *,
    resolved_sql: str,
    test_name: str,
    model_name: str,
) -> tuple[PlanWarning, ...]:
    """Check for unresolved refs and sources in resolved test SQL."""

    warnings: list[PlanWarning] = []
    ref_match: re.Match[str]
    for ref_match in _REF_PATTERN.finditer(resolved_sql):
        ref_name: str = ref_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f' references __ref("{ref_name}") which has'
                    f" no mock and is not in the expected chain"
                ),
            )
        )
    source_match: re.Match[str]
    for source_match in _SOURCE_PATTERN.finditer(resolved_sql):
        source_name: str = source_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f' references __source("{source_name}") which'
                    f" has no mock"
                ),
            )
        )
    seed_match: re.Match[str]
    for seed_match in _SEED_PATTERN.finditer(resolved_sql):
        seed_name: str = seed_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f' references __seed("{seed_name}") which'
                    f" has no mock"
                ),
            )
        )
    dbt_ref_match: re.Match[str]
    for dbt_ref_match in _DBT_REF_PATTERN.finditer(resolved_sql):
        dbt_ref_name: str = _dbt_ref_fixture_name(
            package_name=dbt_ref_match.group(1), model_name=dbt_ref_match.group(2)
        )
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}' references "
                    f"__dbt_ref__{dbt_ref_name} which has no mock"
                ),
            )
        )
    return tuple(warnings)


def _wrap_mock_with_helpers(
    *,
    mock_body: str,
    helper_with: str,
) -> str:
    """Wrap mock CTE body with helper CTEs as a subquery."""

    if helper_with:
        return f"({helper_with} {mock_body})"
    return f"({mock_body})"


def _build_helper_with_clause(
    helper_ctes: tuple[CompileSqlTestCte, ...],
) -> str:
    """Build a WITH clause from helper CTEs."""

    if not helper_ctes:
        return ""
    parts: list[str] = []
    cte: CompileSqlTestCte
    for cte in helper_ctes:
        parts.append(f"{cte.name} AS ({cte.sql_body})")
    return "WITH " + ", ".join(parts)


def _topo_sort_expected(
    *,
    expected_names: tuple[str, ...],
    model_map: dict[str, CompiledModel],
) -> tuple[str, ...]:
    """Sort expected model names in dependency order."""

    expected_set: frozenset[str] = frozenset(expected_names)
    deps: dict[str, set[str]] = {}
    name: str
    for name in expected_names:
        model: CompiledModel | None = model_map.get(name)
        if model is None:
            deps[name] = set()
            continue
        model_refs: set[str] = set()
        match: re.Match[str]
        for match in _REF_PATTERN.finditer(model.query_sql):
            ref_name: str = match.group(1)
            if ref_name in expected_set:
                model_refs.add(ref_name)
        deps[name] = model_refs

    ordered: list[str] = []
    visited: set[str] = set()

    def _visit(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        dep: str
        for dep in sorted(deps.get(node, set())):
            _visit(dep)
        ordered.append(node)

    for name in sorted(expected_names):
        _visit(name)

    return tuple(ordered)


def _extract_mock_refs(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock ref CTE bodies keyed by model name."""

    result: dict[str, str] = {}
    cte: CompileSqlTestCte
    for cte in test.authored_ctes:
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(REF_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_sources(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock source CTE bodies keyed by source name."""

    result: dict[str, str] = {}
    cte: CompileSqlTestCte
    for cte in test.authored_ctes:
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(SOURCE_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_seeds(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock seed CTE bodies keyed by seed name."""

    result: dict[str, str] = {}
    cte: CompileSqlTestCte
    for cte in test.authored_ctes:
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(SEED_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_dbt_refs(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock dbt ref CTE bodies keyed by fixture name."""

    result: dict[str, str] = {}
    cte: CompileSqlTestCte
    for cte in test.authored_ctes:
        if cte.name.startswith(DBT_REF_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(DBT_REF_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _dbt_ref_fixture_name(*, package_name: str, model_name: str | None) -> str:
    if model_name is None:
        return package_name
    return f"{package_name}__{model_name}"


def _extract_helper_ctes(
    test: CompiledSqlTest,
) -> tuple[CompileSqlTestCte, ...]:
    """Extract helper CTEs (not mock refs, not mock sources)."""

    helpers: list[CompileSqlTestCte] = []
    cte: CompileSqlTestCte
    for cte in test.authored_ctes:
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(DBT_REF_TEST_CTE_PREFIX):
            continue
        if cte.name.startswith(ASSERT_TEST_CTE_PREFIX):
            continue
        helpers.append(cte)
    return tuple(helpers)


def _extract_expected_ctes(
    test: CompiledSqlTest,
) -> dict[str, str]:
    """Build expected model name to CTE SQL body mapping.

    Expected CTEs are not in authored_ctes. They are reconstructed
    from the test's raw sql_body by scanning for __expected__ prefixed CTEs.
    """

    result: dict[str, str] = {}
    pattern: re.Pattern[str] = re.compile(
        r"(__expected__\w+)\s+AS\s*\(((?:[^()]*|\((?:[^()]*|\([^()]*\))*\))*)\)",
        re.IGNORECASE,
    )
    match: re.Match[str]
    for match in pattern.finditer(test.sql_body):
        cte_name: str = match.group(1)
        model_name: str = cte_name.removeprefix(EXPECTED_TEST_CTE_PREFIX)
        cte_body: str = match.group(2).strip()
        result[model_name] = cte_body
    return result


def _extract_assertion_ctes(
    test: CompiledSqlTest,
) -> dict[str, str]:
    result: dict[str, str] = {}
    cte: CompileSqlTestCte
    for cte in test.assertion_ctes:
        assertion_name: str = cte.name.removeprefix(ASSERT_TEST_CTE_PREFIX)
        result[assertion_name] = cte.sql_body
    return result
