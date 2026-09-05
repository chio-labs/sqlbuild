"""Test chain resolution for SQL-native unit tests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.constants import (
    ASSERT_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.planner._helpers.resolve.refs import (
    resolve_table_function_references,
    resolve_udf_references,
)
from sqlbuild.compiler.planner._helpers.sql_tests.analysis_assembly import (
    try_resolve_test_model_sql_with_sql_analysis,
)
from sqlbuild.compiler.planner._helpers.sql_tests.comments import (
    replace_uncommented_pattern,
    uncommented_matches_by_pattern,
    uncommented_pattern_matches,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    ChainStep,
    PlanWarning,
    SqlAnalysisResolvedTestSql,
    SqlTestAssertionStep,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.references.main._quoted_reference_call_pattern import (
    quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import SqlReferenceKind

_REF_PATTERN: re.Pattern[str] = re.compile(
    quoted_reference_call_pattern(SqlReferenceKind.REF).pattern, re.IGNORECASE
)
_SOURCE_PATTERN: re.Pattern[str] = re.compile(
    quoted_reference_call_pattern(SqlReferenceKind.SOURCE).pattern, re.IGNORECASE
)
_SEED_PATTERN: re.Pattern[str] = re.compile(
    quoted_reference_call_pattern(SqlReferenceKind.SEED).pattern, re.IGNORECASE
)
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(
    rf'{reference_call_prefix_pattern_text(SqlReferenceKind.DBT_REF)}"([^"]+)"'
    r'(?:,\s*"([^"]+)")?\)',
    re.IGNORECASE,
)
_TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(
    reference_call_prefix_pattern_text(SqlReferenceKind.TABLE_FUNCTION), re.IGNORECASE
)
_LEADING_WITH_PATTERN: re.Pattern[str] = re.compile(r"^\s*WITH\b", re.IGNORECASE)


@dataclass
class _TextualChainResolver:
    model_names: tuple[str, ...]
    model_map: dict[str, CompiledModel]
    test: CompiledSqlTest
    mock_refs: dict[str, str]
    mock_sources: dict[str, str]
    mock_seeds: dict[str, str]
    mock_dbt_refs: dict[str, str]
    helper_ctes: tuple[CompileSqlTestCte, ...]
    function_locations: dict[str, CompiledRelationLocation]
    adapter: BaseAdapter
    resolved: dict[str, str] = field(default_factory=dict)
    step_sql: dict[str, str] = field(default_factory=dict)
    reachable_mocks: set[str] = field(default_factory=set)

    def ensure_through(self, count: int) -> None:
        for model_name in self.model_names[:count]:
            if model_name in self.resolved:
                continue
            model: CompiledModel | None = self.model_map.get(model_name)
            if model is None:
                continue
            sql: str
            reached: frozenset[str]
            sql, reached = _resolve_test_model_sql(
                query_sql=_resolve_test_model_query_sql(model=model, test=self.test),
                mock_refs=self.mock_refs,
                mock_sources=self.mock_sources,
                mock_seeds=self.mock_seeds,
                mock_dbt_refs=self.mock_dbt_refs,
                helper_ctes=self.helper_ctes,
                resolved_chain=self.resolved,
                function_locations=self.function_locations,
                adapter=self.adapter,
            )
            self.reachable_mocks.update(reached)
            self.step_sql[model_name] = sql
            self.resolved[model_name] = f"({sql})"

    def resolve_all(self) -> dict[str, str]:
        self.ensure_through(len(self.model_names))
        return self.resolved


def plan_test(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    sql_analysis_enabled: bool = False,
) -> tuple[SqlTestPlanEntry, tuple[PlanWarning, ...]]:
    """Build a test plan entry with chained resolution."""

    if isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        function_locations: dict[str, CompiledRelationLocation] = {
            function.name: function.destination for function in project.functions
        }
        return (
            _plan_direct_logic_test(
                test=test,
                function_locations=function_locations,
                function_deps=_direct_function_deps(test=test, project=project),
                adapter=adapter,
                sql_analysis_enabled=sql_analysis_enabled,
            ),
            (),
        )

    model_payload: CompiledModelSqlTestPayload = test.payload

    model_map: dict[str, CompiledModel] = {m.name: m for m in project.models}
    function_locations: dict[str, CompiledRelationLocation] = {
        function.name: function.destination for function in project.functions
    }
    qualified_function_locations: dict[str, str] = {
        name: target.qualified_name
        for name, target in function_locations.items()
        if target.qualified_name is not None
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
        dict.fromkeys((*model_payload.expected_model_names, *assertion_target_names))
    )
    ordered_names: tuple[str, ...] = _topo_sort_model_chain(
        expected_names=expected_names,
        model_map=model_map,
        model_query_overrides=model_payload.model_query_overrides,
        mock_ref_names=frozenset(mock_refs),
    )

    warnings: list[PlanWarning] = []
    reachable_mocks: set[str] = set()
    sql_analysis_resolved: dict[str, SqlAnalysisResolvedTestSql] = {}
    function_deps: list[CompiledObjectKey] = []
    textual_chain: _TextualChainResolver = _TextualChainResolver(
        model_names=ordered_names,
        model_map=model_map,
        test=test,
        mock_refs=mock_refs,
        mock_sources=mock_sources,
        mock_seeds=mock_seeds,
        mock_dbt_refs=mock_dbt_refs,
        helper_ctes=helper_ctes,
        function_locations=function_locations,
        adapter=adapter,
    )

    chain_steps: list[ChainStep] = []
    model_index: int
    model_name: str
    for model_index, model_name in enumerate(ordered_names):
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
            dep
            for dep in model.deps
            if dep.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}
        )

        query_sql: str = _resolve_test_model_query_sql(model=model, test=test)
        step_sql: str | None = None
        if sql_analysis_enabled:
            sql_analysis_sql: SqlAnalysisResolvedTestSql | None = (
                try_resolve_test_model_sql_with_sql_analysis(
                    query_sql=query_sql,
                    mock_refs=mock_refs,
                    mock_sources=mock_sources,
                    mock_seeds=mock_seeds,
                    mock_dbt_refs=mock_dbt_refs,
                    function_locations=qualified_function_locations,
                    helper_ctes=helper_ctes,
                    resolved_chain=sql_analysis_resolved,
                    file_label=str(test.test_file.relative_path),
                    sql_analysis_dialect=adapter.sql_analysis_dialect(),
                )
            )
            if sql_analysis_sql is not None:
                step_sql = sql_analysis_sql.resolved_sql
                sql_analysis_resolved[model_name] = sql_analysis_sql
                reachable_mocks.update(sql_analysis_sql.reachable_mock_names)
        if step_sql is None:
            textual_chain.ensure_through(model_index + 1)
            step_sql = textual_chain.step_sql[model_name]

        unresolved_warnings: tuple[PlanWarning, ...] = _validate_resolved_sql(
            resolved_sql=step_sql,
            test_name=test.name,
            model_name=model_name,
        )
        warnings.extend(unresolved_warnings)

        expected_cte_sql: str = expected_map.get(model_name, "")
        chain_steps.append(
            ChainStep(
                model_name=model_name,
                resolved_sql=step_sql,
                expected_cte_sql=expected_cte_sql or None,
            )
        )

    assertion_steps: tuple[SqlTestAssertionStep, ...] = _build_assertion_steps(
        assertion_map=assertion_map,
        test=test,
        function_locations=function_locations,
        qualified_function_locations=qualified_function_locations,
        helper_ctes=helper_ctes,
        textual_chain=textual_chain,
        sql_analysis_resolved=sql_analysis_resolved,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
    )
    reachable_mocks.update(textual_chain.reachable_mocks)

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
        source_path=test.source_path,
        block_index=test.block_index,
        parent_name=test.parent_name,
        case_name=test.case_name,
        case_index=test.case_index,
        case_fingerprint=test.case_fingerprint,
        parameter_schema=test.parameter_schema,
        parameter_values=test.parameter_values,
        chain=tuple(chain_steps),
        assertions=assertion_steps,
        scope_deps=test.scope_deps,
        function_deps=_dedupe_function_deps(function_deps),
        sql_analysis_enabled=sql_analysis_enabled,
    )
    return entry, tuple(warnings)


def _build_assertion_steps(
    *,
    assertion_map: dict[str, str],
    test: CompiledSqlTest,
    function_locations: dict[str, CompiledRelationLocation],
    qualified_function_locations: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    textual_chain: _TextualChainResolver,
    sql_analysis_resolved: dict[str, SqlAnalysisResolvedTestSql],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[SqlTestAssertionStep, ...]:
    mock_refs: dict[str, str] = _extract_mock_refs(test)
    mock_sources: dict[str, str] = _extract_mock_sources(test)
    mock_seeds: dict[str, str] = _extract_mock_seeds(test)
    mock_dbt_refs: dict[str, str] = _extract_mock_dbt_refs(test)
    assertion_steps: list[SqlTestAssertionStep] = []
    assertion_name: str
    assertion_sql: str
    for assertion_name, assertion_sql in assertion_map.items():
        resolved_assertion_sql: str | None = None
        if sql_analysis_enabled:
            analyzed_assertion_sql: SqlAnalysisResolvedTestSql | None = (
                try_resolve_test_model_sql_with_sql_analysis(
                    query_sql=assertion_sql,
                    mock_refs=mock_refs,
                    mock_sources=mock_sources,
                    mock_seeds=mock_seeds,
                    mock_dbt_refs=mock_dbt_refs,
                    function_locations=qualified_function_locations,
                    helper_ctes=helper_ctes,
                    resolved_chain=sql_analysis_resolved,
                    file_label=str(test.test_file.relative_path),
                    sql_analysis_dialect=adapter.sql_analysis_dialect(),
                )
            )
            if analyzed_assertion_sql is not None and not _has_unresolved_test_reference(
                analyzed_assertion_sql.resolved_sql
            ):
                resolved_assertion_sql = analyzed_assertion_sql.resolved_sql
        if resolved_assertion_sql is None:
            resolved_assertion_sql = _resolve_assertion_sql(
                sql=assertion_sql,
                resolved_chain=textual_chain.resolve_all(),
                mock_refs=mock_refs,
                mock_sources=mock_sources,
                mock_seeds=mock_seeds,
                mock_dbt_refs=mock_dbt_refs,
                helper_ctes=helper_ctes,
                function_locations=function_locations,
                adapter=adapter,
            )
        assertion_steps.append(
            SqlTestAssertionStep(
                name=assertion_name,
                resolved_sql=resolved_assertion_sql,
            )
        )
    return tuple(assertion_steps)


def _plan_direct_logic_test(
    *,
    test: CompiledSqlTest,
    function_locations: dict[str, CompiledRelationLocation],
    function_deps: tuple[CompiledObjectKey, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> SqlTestPlanEntry:
    if not isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        raise PlannerInputError(f"test '{test.name}' is not a direct-logic SQL test")
    helper_ctes: tuple[CompileSqlTestCte, ...] = test.payload.helper_ctes
    helper_with: str = _build_helper_with_clause(helper_ctes)
    actual_sql: str = test.payload.actual_cte.sql_body
    if test.payload.mode == SqlTestMode.UDF:
        actual_sql = resolve_udf_references(
            query_sql=actual_sql,
            function_locations=function_locations,
            adapter=adapter,
        )
    if test.payload.mode == SqlTestMode.TABLE_FN:
        actual_sql = resolve_table_function_references(
            query_sql=actual_sql,
            function_locations=function_locations,
            adapter=adapter,
        )
    label: str = test.payload.mode.value
    return SqlTestPlanEntry(
        key=test.key,
        name=test.name,
        source_path=test.source_path,
        block_index=test.block_index,
        parent_name=test.parent_name,
        case_name=test.case_name,
        case_index=test.case_index,
        case_fingerprint=test.case_fingerprint,
        parameter_schema=test.parameter_schema,
        parameter_values=test.parameter_values,
        chain=(
            ChainStep(
                model_name=f"{label} {test.name}",
                resolved_sql=_wrap_direct_logic_sql(
                    sql=actual_sql,
                    helper_with=helper_with,
                ),
                expected_cte_sql=_wrap_direct_logic_sql(
                    sql=test.payload.expected_cte.sql_body,
                    helper_with=helper_with,
                ),
            ),
        ),
        scope_deps=test.scope_deps,
        function_deps=function_deps,
        sql_analysis_enabled=sql_analysis_enabled,
    )


def _direct_function_deps(
    *, test: CompiledSqlTest, project: CompiledProject
) -> tuple[CompiledObjectKey, ...]:
    if not isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        return ()
    resource_type: CompiledResourceType | None = (
        CompiledResourceType.UDF
        if test.payload.mode == SqlTestMode.UDF
        else CompiledResourceType.TABLE_FN
        if test.payload.mode == SqlTestMode.TABLE_FN
        else None
    )
    if resource_type is None:
        return ()
    tested_names: frozenset[str] = frozenset(test.payload.tested_resource_names)
    return tuple(
        function.key
        for function in project.functions
        if function.key.resource_type == resource_type and function.name in tested_names
    )


def _wrap_direct_logic_sql(*, sql: str, helper_with: str) -> str:
    if helper_with:
        return f"{helper_with} {sql}"
    return sql


def _extract_assertion_ref_targets(*, assertion_map: dict[str, str]) -> tuple[str, ...]:
    targets: list[str] = []
    sql: str
    for sql in assertion_map.values():
        match: re.Match[str]
        for match in uncommented_pattern_matches(pattern=_REF_PATTERN, sql=sql):
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
    function_locations: dict[str, CompiledRelationLocation],
    adapter: BaseAdapter,
) -> str:
    assertion_resolved_chain: dict[str, str]
    assertion_chain_ctes: tuple[str, ...]
    assertion_resolved_chain, assertion_chain_ctes = _build_assertion_chain_ctes(
        assertion_sql=sql,
        resolved_chain=resolved_chain,
        requires_flat_ctes=adapter.requires_derived_table_aliases(),
    )
    resolved_sql: str
    resolved_sql, _ = _resolve_test_model_sql(
        query_sql=sql,
        mock_refs=mock_refs,
        mock_sources=mock_sources,
        mock_seeds=mock_seeds,
        mock_dbt_refs=mock_dbt_refs,
        helper_ctes=helper_ctes,
        resolved_chain=assertion_resolved_chain,
        function_locations=function_locations,
        adapter=adapter,
    )
    if assertion_chain_ctes:
        return f"WITH {', '.join(assertion_chain_ctes)} {resolved_sql}"
    return resolved_sql


def _build_assertion_chain_ctes(
    *,
    assertion_sql: str,
    resolved_chain: dict[str, str],
    requires_flat_ctes: bool,
) -> tuple[dict[str, str], tuple[str, ...]]:
    if requires_flat_ctes and _LEADING_WITH_PATTERN.search(assertion_sql) is not None:
        raise PlannerInputError(
            "SQL test assertion fallback cannot safely flatten an assertion beginning with WITH"
        )
    assertion_resolved_chain: dict[str, str] = {}
    cte_parts: list[str] = []
    seen_names: set[str] = set()
    match: re.Match[str]
    for match in uncommented_pattern_matches(pattern=_REF_PATTERN, sql=assertion_sql):
        name: str = match.group(1)
        if name in seen_names or name not in resolved_chain:
            continue
        seen_names.add(name)
        cte_name: str = f"{REF_TEST_CTE_PREFIX}{name}"
        resolved_sql: str = resolved_chain[name].strip()
        if resolved_sql.startswith("(") and resolved_sql.endswith(")"):
            resolved_sql = resolved_sql[1:-1].strip()
        if requires_flat_ctes and _LEADING_WITH_PATTERN.search(resolved_sql) is not None:
            raise PlannerInputError(
                "SQL test assertion fallback cannot safely flatten a referenced model beginning "
                "with WITH"
            )
        assertion_resolved_chain[name] = cte_name
        cte_parts.append(f"{cte_name} AS ({resolved_sql})")
    return assertion_resolved_chain, tuple(cte_parts)


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

    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        raise PlannerInputError(f"test '{test.name}' is not a model SQL test")
    return test.payload.model_query_overrides.get(model.name, model.query_sql)


def _resolve_test_model_sql(
    *,
    query_sql: str,
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    mock_dbt_refs: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    resolved_chain: dict[str, str],
    function_locations: dict[str, CompiledRelationLocation],
    adapter: BaseAdapter,
) -> tuple[str, frozenset[str]]:
    """Replace refs and sources in model SQL and return it with reached mock names."""

    ref_matches: tuple[re.Match[str], ...]
    source_matches: tuple[re.Match[str], ...]
    seed_matches: tuple[re.Match[str], ...]
    dbt_ref_matches: tuple[re.Match[str], ...]
    ref_matches, source_matches, seed_matches, dbt_ref_matches = uncommented_matches_by_pattern(
        patterns=(_REF_PATTERN, _SOURCE_PATTERN, _SEED_PATTERN, _DBT_REF_PATTERN),
        sql=query_sql,
    )
    reachable_mocks: set[str] = {
        match.group(1)
        for match in ref_matches
        if match.group(1) in mock_refs and match.group(1) not in resolved_chain
    }
    reachable_mocks.update(
        match.group(1) for match in source_matches if match.group(1) in mock_sources
    )
    reachable_mocks.update(match.group(1) for match in seed_matches if match.group(1) in mock_seeds)
    reachable_mocks.update(
        name
        for match in dbt_ref_matches
        if (name := _dbt_ref_fixture_name(package_name=match.group(1), model_name=match.group(2)))
        in mock_dbt_refs
    )
    helper_with: str = _build_helper_with_clause(helper_ctes)

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        if ref_name in resolved_chain:
            return resolved_chain[ref_name]
        if ref_name in mock_refs:
            mock_body: str = mock_refs[ref_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    def _replace_source(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        if source_name in mock_sources:
            mock_body: str = mock_sources[source_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    def _replace_seed(match: re.Match[str]) -> str:
        seed_name: str = match.group(1)
        if seed_name in mock_seeds:
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
            mock_body: str = mock_dbt_refs[dbt_ref_name]
            return _wrap_mock_with_helpers(
                mock_body=mock_body,
                helper_with=helper_with,
            )
        return match.group(0)

    result: str = replace_uncommented_pattern(
        pattern=_REF_PATTERN, replacement=_replace_ref, sql=query_sql
    )
    result = replace_uncommented_pattern(
        pattern=_SOURCE_PATTERN, replacement=_replace_source, sql=result
    )
    result = replace_uncommented_pattern(
        pattern=_SEED_PATTERN, replacement=_replace_seed, sql=result
    )
    result = replace_uncommented_pattern(
        pattern=_DBT_REF_PATTERN, replacement=_replace_dbt_ref, sql=result
    )
    result = resolve_udf_references(
        query_sql=result,
        function_locations=function_locations,
        adapter=adapter,
    )
    result = resolve_table_function_references(
        query_sql=result,
        function_locations=function_locations,
        adapter=adapter,
    )
    return result, frozenset(reachable_mocks)


def _validate_resolved_sql(
    *,
    resolved_sql: str,
    test_name: str,
    model_name: str,
) -> tuple[PlanWarning, ...]:
    """Check for unresolved refs and sources in resolved test SQL."""

    patterns: tuple[re.Pattern[str], ...] = (
        _REF_PATTERN,
        _SOURCE_PATTERN,
        _SEED_PATTERN,
        _DBT_REF_PATTERN,
    )
    if not any(pattern.search(resolved_sql) for pattern in patterns):
        return ()
    warnings: list[PlanWarning] = []
    ref_matches: tuple[re.Match[str], ...]
    source_matches: tuple[re.Match[str], ...]
    seed_matches: tuple[re.Match[str], ...]
    dbt_ref_matches: tuple[re.Match[str], ...]
    ref_matches, source_matches, seed_matches, dbt_ref_matches = uncommented_matches_by_pattern(
        patterns=patterns,
        sql=resolved_sql,
    )
    ref_match: re.Match[str]
    for ref_match in ref_matches:
        ref_name: str = ref_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f" references {SqlReferenceKind.REF.example_call(ref_name)} which has"
                    f" no mock and is not in the expected chain"
                ),
            )
        )
    source_match: re.Match[str]
    for source_match in source_matches:
        source_name: str = source_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f" references {SqlReferenceKind.SOURCE.example_call(source_name)} which"
                    f" has no mock"
                ),
            )
        )
    seed_match: re.Match[str]
    for seed_match in seed_matches:
        seed_name: str = seed_match.group(1)
        warnings.append(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.ERROR,
                message=(
                    f"test '{test_name}': model '{model_name}'"
                    f" references {SqlReferenceKind.SEED.example_call(seed_name)} which"
                    f" has no mock"
                ),
            )
        )
    dbt_ref_match: re.Match[str]
    for dbt_ref_match in dbt_ref_matches:
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


def _has_unresolved_test_reference(sql: str) -> bool:
    reference_matches: tuple[tuple[re.Match[str], ...], ...] = uncommented_matches_by_pattern(
        patterns=(
            _REF_PATTERN,
            _SOURCE_PATTERN,
            _SEED_PATTERN,
            _DBT_REF_PATTERN,
            _TABLE_FUNCTION_PATTERN,
        ),
        sql=sql,
    )
    return any(reference_matches)


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


def _topo_sort_model_chain(
    *,
    expected_names: tuple[str, ...],
    model_map: dict[str, CompiledModel],
    model_query_overrides: dict[str, str],
    mock_ref_names: frozenset[str],
) -> tuple[str, ...]:
    """Sort asserted models and their unmocked model dependencies in execution order."""

    ordered: list[str] = []
    visited: set[str] = set()

    def _visit(*, node: str, seen: set[str], result: list[str]) -> tuple[set[str], list[str]]:
        if node in seen:
            return seen, result
        seen = seen | {node}
        model: CompiledModel | None = model_map.get(node)
        if model is not None:
            dependency_names: set[str] = _test_model_dependency_names(
                model=model,
                query_override=model_query_overrides.get(node),
                model_map=model_map,
                mock_ref_names=mock_ref_names,
            )
            dependency_name: str
            for dependency_name in sorted(dependency_names):
                seen, result = _visit(node=dependency_name, seen=seen, result=result)
        return seen, [*result, node]

    for name in sorted(expected_names):
        visited, ordered = _visit(node=name, seen=visited, result=ordered)

    return tuple(ordered)


def _test_model_dependency_names(
    *,
    model: CompiledModel,
    query_override: str | None,
    model_map: dict[str, CompiledModel],
    mock_ref_names: frozenset[str],
) -> set[str]:
    if query_override is not None:
        candidates: set[str] = {
            match.group(1)
            for match in uncommented_pattern_matches(pattern=_REF_PATTERN, sql=query_override)
        }
    else:
        candidates = {
            dependency.name
            for dependency in model.deps
            if dependency.resource_type == CompiledResourceType.MODEL
        }
    return {name for name in candidates if name not in mock_ref_names and name in model_map}


def _extract_mock_refs(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock ref CTE bodies keyed by model name."""

    result: dict[str, str] = {}
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return result
    cte: CompileSqlTestCte
    for cte in test.payload.authored_ctes:
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(REF_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_sources(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock source CTE bodies keyed by source name."""

    result: dict[str, str] = {}
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return result
    cte: CompileSqlTestCte
    for cte in test.payload.authored_ctes:
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(SOURCE_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_seeds(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock seed CTE bodies keyed by seed name."""

    result: dict[str, str] = {}
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return result
    cte: CompileSqlTestCte
    for cte in test.payload.authored_ctes:
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            name: str = cte.name.removeprefix(SEED_TEST_CTE_PREFIX)
            result[name] = cte.sql_body
    return result


def _extract_mock_dbt_refs(test: CompiledSqlTest) -> dict[str, str]:
    """Extract mock dbt ref CTE bodies keyed by fixture name."""

    result: dict[str, str] = {}
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return result
    cte: CompileSqlTestCte
    for cte in test.payload.authored_ctes:
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
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return tuple(helpers)
    cte: CompileSqlTestCte
    for cte in test.payload.authored_ctes:
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
    """Build expected model name to CTE SQL body mapping."""

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
    if not isinstance(test.payload, CompiledModelSqlTestPayload):
        return result
    cte: CompileSqlTestCte
    for cte in test.payload.assertion_ctes:
        assertion_name: str = cte.name.removeprefix(ASSERT_TEST_CTE_PREFIX)
        result[assertion_name] = cte.sql_body
    return result
