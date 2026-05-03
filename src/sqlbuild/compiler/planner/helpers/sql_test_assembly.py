"""Test chain resolution for SQL-native unit tests."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.constants import (
    EXPECTED_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.planner.models import (
    ChainStep,
    PlanWarning,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import WarningSeverity

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')


def plan_test(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a test plan entry with chained resolution."""

    model_map: dict[str, CompiledModel] = {m.name: m for m in project.models}
    mock_refs: dict[str, str] = _extract_mock_refs(test)
    mock_sources: dict[str, str] = _extract_mock_sources(test)
    helper_ctes: tuple[CompileSqlTestCte, ...] = _extract_helper_ctes(test)
    expected_map: dict[str, str] = _extract_expected_ctes(test)

    expected_names: tuple[str, ...] = test.expected_model_names
    ordered_names: tuple[str, ...] = _topo_sort_expected(
        expected_names=expected_names,
        model_map=model_map,
    )

    warnings: list[PlanWarning] = []
    reachable_mocks: set[str] = set()
    resolved: dict[str, str] = {}

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

        step_sql: str = _resolve_test_model_sql(
            query_sql=model.query_sql,
            mock_refs=mock_refs,
            mock_sources=mock_sources,
            helper_ctes=helper_ctes,
            resolved_chain=resolved,
            reachable_mocks=reachable_mocks,
        )

        unresolved_warnings: tuple[PlanWarning, ...] = _validate_resolved_sql(
            resolved_sql=step_sql,
            test_name=test.name,
            model_name=model_name,
        )
        warnings.extend(unresolved_warnings)

        resolved[model_name] = f"({step_sql})"

        expected_cte_sql: str = expected_map.get(model_name, "")
        chain_steps.append(
            ChainStep(
                model_name=model_name,
                resolved_sql=step_sql,
                expected_cte_sql=expected_cte_sql,
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

    entry: SqlTestPlanEntry = SqlTestPlanEntry(
        key=test.key,
        name=test.name,
        chain=tuple(chain_steps),
        scope_deps=test.scope_deps,
    )
    return entry, tuple(warnings)


def _resolve_test_model_sql(
    *,
    query_sql: str,
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    resolved_chain: dict[str, str],
    reachable_mocks: set[str],
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

    result: str = _REF_PATTERN.sub(_replace_ref, query_sql)
    result = _SOURCE_PATTERN.sub(_replace_source, result)
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
