"""Optional Polyglot-backed SQL-native test assembly helpers."""

from __future__ import annotations

import logging
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.planner._helpers.scenario.relations import (
    _replace_relation_markers_in_polyglot_dict,
)
from sqlbuild.compiler.planner.models import SqlAnalysisResolvedTestSql
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")


class _TestAssemblyState:
    def __init__(self, names: set[str]) -> None:
        self.names = names
        self.ctes: OrderedDict[str, str] = OrderedDict()
        self.reached: set[str] = set()

    def add_name(self, name: str) -> None:
        self.names.add(name)

    def add_reached(self, name: str) -> None:
        self.reached.add(name)

    def setdefault_cte(self, *, name: str, sql: str) -> None:
        self.ctes.setdefault(name, sql)


class _TestMarkerResolver:
    def __init__(
        self,
        *,
        state: _TestAssemblyState,
        mock_refs: dict[str, str],
        mock_sources: dict[str, str],
        mock_seeds: dict[str, str],
        mock_dbt_refs: dict[str, str],
        function_locations: dict[str, str],
        helper_ctes: tuple[CompileSqlTestCte, ...],
        resolved_chain: dict[str, SqlAnalysisResolvedTestSql],
        file_label: str,
    ) -> None:
        self.state = state
        self.mock_refs = mock_refs
        self.mock_sources = mock_sources
        self.mock_seeds = mock_seeds
        self.mock_dbt_refs = mock_dbt_refs
        self.function_locations = function_locations
        self.helper_ctes = helper_ctes
        self.resolved_chain = resolved_chain
        self.file_label = file_label

    def __call__(self, *, function_name: str, referenced_name: str) -> str | None:
        if function_name == SqlReferenceKind.REF.function_name:
            resolved_target: str | None = self._resolved_ref_target(referenced_name=referenced_name)
            if resolved_target is not None:
                return resolved_target
            return self._mock_target(
                generated_name=f"{REF_TEST_CTE_PREFIX}{referenced_name}",
                referenced_name=referenced_name,
                referenced_kind="ref",
                mocks=self.mock_refs,
            )
        if function_name == SqlReferenceKind.SOURCE.function_name:
            return self._mock_target(
                generated_name=f"{SOURCE_TEST_CTE_PREFIX}{referenced_name}",
                referenced_name=referenced_name,
                referenced_kind="source",
                mocks=self.mock_sources,
            )
        if function_name == SqlReferenceKind.SEED.function_name:
            return self._mock_target(
                generated_name=f"{SEED_TEST_CTE_PREFIX}{referenced_name}",
                referenced_name=referenced_name,
                referenced_kind="seed",
                mocks=self.mock_seeds,
            )
        if function_name == SqlReferenceKind.DBT_REF.function_name:
            return self._mock_target(
                generated_name=f"{DBT_REF_TEST_CTE_PREFIX}{referenced_name}",
                referenced_name=referenced_name,
                referenced_kind="dbt_ref",
                mocks=self.mock_dbt_refs,
            )
        if function_name == SqlReferenceKind.UDF.function_name:
            return self.function_locations.get(referenced_name)
        return None

    def _resolved_ref_target(self, *, referenced_name: str) -> str | None:
        chain_sql: SqlAnalysisResolvedTestSql | None = self.resolved_chain.get(referenced_name)
        if chain_sql is None:
            return None
        generated_name: str = f"{REF_TEST_CTE_PREFIX}{referenced_name}"
        self._ensure_available(
            generated_name=generated_name,
            referenced_name=referenced_name,
            referenced_kind="ref",
        )
        dependency_name: str
        dependency_sql: str
        for dependency_name, dependency_sql in chain_sql.generated_ctes.items():
            self.state.setdefault_cte(name=dependency_name, sql=dependency_sql)
            self.state.add_name(dependency_name)
        self.state.setdefault_cte(name=generated_name, sql=chain_sql.cte_body_sql)
        return generated_name

    def _mock_target(
        self,
        *,
        generated_name: str,
        referenced_name: str,
        referenced_kind: str,
        mocks: dict[str, str],
    ) -> str | None:
        mock_body: str | None = mocks.get(referenced_name)
        if mock_body is None:
            return None
        self.state.add_reached(referenced_name)
        self._ensure_available(
            generated_name=generated_name,
            referenced_name=referenced_name,
            referenced_kind=referenced_kind,
        )
        self.state.setdefault_cte(
            name=generated_name, sql=self._wrap_mock_body(mock_body=mock_body)
        )
        return generated_name

    def _ensure_available(
        self,
        *,
        generated_name: str,
        referenced_name: str,
        referenced_kind: str,
    ) -> None:
        if generated_name not in self.state.names:
            self.state.add_name(generated_name)
            return
        if generated_name in self.state.ctes:
            return
        raise CompileInputError(
            f"SQL test '{self.file_label}' defines CTE '{generated_name}', which conflicts with "
            "the "
            f"generated {referenced_kind} CTE for '{referenced_name}'"
        )

    def _wrap_mock_body(self, *, mock_body: str) -> str:
        if not self.helper_ctes:
            return mock_body
        helper_parts: list[str] = []
        helper_cte: CompileSqlTestCte
        for helper_cte in self.helper_ctes:
            helper_parts.append(f"{helper_cte.name} AS ({helper_cte.sql_body})")
        return f"WITH {', '.join(helper_parts)} {mock_body}"


def try_resolve_test_model_sql_with_sql_analysis(
    *,
    query_sql: str,
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    mock_dbt_refs: dict[str, str],
    function_locations: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    resolved_chain: dict[str, SqlAnalysisResolvedTestSql],
    file_label: str,
) -> SqlAnalysisResolvedTestSql | None:
    """Return Polyglot-backed readable test SQL or None on import/parse failure."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    parsed_dict: dict[str, Any] | None = _try_parse_test_query(
        polyglot_module=polyglot_module,
        query_sql=query_sql,
    )
    if parsed_dict is None:
        return None
    state: _TestAssemblyState = _TestAssemblyState(_collect_existing_cte_names(parsed_dict))
    target_for_marker: _TestMarkerResolver = _TestMarkerResolver(
        state=state,
        mock_refs=mock_refs,
        mock_sources=mock_sources,
        mock_seeds=mock_seeds,
        mock_dbt_refs=mock_dbt_refs,
        function_locations=function_locations,
        helper_ctes=helper_ctes,
        resolved_chain=resolved_chain,
        file_label=file_label,
    )
    _replace_relation_markers_in_polyglot_dict(
        node=parsed_dict,
        polyglot_module=polyglot_module,
        sql_analysis_dialect=None,
        target_for_marker=target_for_marker,
    )
    outer_sql: str | None = _render_test_outer_sql(
        polyglot_module=polyglot_module,
        parsed_dict=parsed_dict,
    )
    if outer_sql is None:
        return None

    return _assemble_resolved_test_sql(
        polyglot_module=polyglot_module,
        parsed_dict=parsed_dict,
        generated_ctes=state.ctes,
        outer_sql=outer_sql,
        reachable_mocks=state.reached,
    )


def _try_parse_test_query(*, polyglot_module: Any, query_sql: str) -> dict[str, Any] | None:
    try:
        parsed: Any = polyglot_module.parse_one(query_sql, dialect="generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="sql test assembly parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    return parsed.to_dict()


def _render_test_outer_sql(*, polyglot_module: Any, parsed_dict: dict[str, Any]) -> str | None:
    transformed_without_with: dict[str, Any] = deepcopy(parsed_dict)
    without_with_select: dict[str, Any] | None = _root_select(transformed_without_with)
    if without_with_select is not None:
        without_with_select["with"] = None
    return _generate_one(polyglot_module=polyglot_module, expression=transformed_without_with)


def _assemble_resolved_test_sql(
    *,
    polyglot_module: Any,
    parsed_dict: dict[str, Any],
    generated_ctes: OrderedDict[str, str],
    outer_sql: str,
    reachable_mocks: set[str],
) -> SqlAnalysisResolvedTestSql | None:
    cte_parts: list[str] = [f"{name} AS ({sql})" for name, sql in generated_ctes.items()]
    transformed_select: dict[str, Any] | None = _root_select(parsed_dict)
    transformed_with: dict[str, Any] | None = (
        transformed_select.get("with") if transformed_select is not None else None
    )
    if isinstance(transformed_with, dict):
        cte: dict[str, Any]
        for cte in transformed_with.get("ctes", ()):
            cte_name: str | None = _cte_name(cte)
            cte_sql: str | None = _generate_one(
                polyglot_module=polyglot_module,
                expression={"cte": cte},
            )
            if cte_name is not None and cte_sql is not None:
                cte_parts.append(cte_sql)
    cte_body_sql: str | None = _generate_one(
        polyglot_module=polyglot_module, expression=parsed_dict
    )
    if cte_body_sql is None:
        return None
    if not cte_parts:
        return SqlAnalysisResolvedTestSql(
            resolved_sql=cte_body_sql,
            cte_body_sql=cte_body_sql,
            generated_ctes=generated_ctes,
            reachable_mock_names=frozenset(reachable_mocks),
        )
    return SqlAnalysisResolvedTestSql(
        resolved_sql=f"WITH {', '.join(cte_parts)} {outer_sql}",
        cte_body_sql=cte_body_sql,
        generated_ctes=generated_ctes,
        reachable_mock_names=frozenset(reachable_mocks),
    )


def _collect_existing_cte_names(parsed_dict: dict[str, Any]) -> set[str]:
    generated_names: set[str] = set()
    root_select: dict[str, Any] | None = _root_select(parsed_dict)
    existing_with: dict[str, Any] | None = (
        root_select.get("with") if root_select is not None else None
    )
    if isinstance(existing_with, dict):
        cte: dict[str, Any]
        for cte in existing_with.get("ctes", ()):
            alias: Any | None = cte.get("alias")
            if not isinstance(alias, dict):
                continue
            alias_name: Any | None = alias.get("name")
            if alias_name is not None:
                generated_names.add(str(alias_name))
    return generated_names


def _root_select(parsed_dict: dict[str, Any]) -> dict[str, Any] | None:
    select_payload: Any | None = parsed_dict.get("select")
    return select_payload if isinstance(select_payload, dict) else None


def _cte_name(cte: dict[str, Any]) -> str | None:
    alias: Any | None = cte.get("alias")
    if not isinstance(alias, dict):
        return None
    name: Any | None = alias.get("name")
    return str(name) if name is not None else None


def _generate_one(*, polyglot_module: Any, expression: Any) -> str | None:
    try:
        generated: list[str] = polyglot_module.generate(expression, dialect="generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="sql test assembly generation failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if len(generated) != 1:
        return None
    return generated[0]
