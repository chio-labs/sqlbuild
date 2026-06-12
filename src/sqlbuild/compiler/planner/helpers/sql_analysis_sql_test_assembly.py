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
from sqlbuild.compiler.compile.models.sql_tests import CompileSqlTestCte
from sqlbuild.compiler.planner.helpers.scenario_relations import (
    _replace_relation_markers_in_polyglot_dict,
)
from sqlbuild.compiler.planner.models import SqlAnalysisResolvedTestSql
from sqlbuild.shared.helpers.diagnostics_logging import log_debug_event
from sqlbuild.shared.helpers.polyglot import import_polyglot_sql
from sqlbuild.shared.types import SqlReferenceKind

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")


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
    reachable_mocks: set[str],
    file_label: str,
) -> SqlAnalysisResolvedTestSql | None:
    """Return Polyglot-backed readable test SQL or None on import/parse failure."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None

    try:
        parsed: Any = polyglot_module.parse_one(query_sql, dialect="generic")
    except Exception as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "sql test assembly parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return None

    parsed_dict: dict[str, Any] = parsed.to_dict()
    generated_ctes: OrderedDict[str, str] = OrderedDict()
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

    def _ensure_available(generated_name: str, referenced_name: str, referenced_kind: str) -> None:
        if generated_name not in generated_names:
            generated_names.add(generated_name)
            return
        if generated_name in generated_ctes:
            return
        raise CompileInputError(
            f"SQL test '{file_label}' defines CTE '{generated_name}', which conflicts with the "
            f"generated {referenced_kind} CTE for '{referenced_name}'"
        )

    def _wrap_mock_body(mock_body: str) -> str:
        if not helper_ctes:
            return mock_body
        helper_parts: list[str] = []
        helper_cte: CompileSqlTestCte
        for helper_cte in helper_ctes:
            helper_parts.append(f"{helper_cte.name} AS ({helper_cte.sql_body})")
        return f"WITH {', '.join(helper_parts)} {mock_body}"

    def _target_for_marker(function_name: str, referenced_name: str) -> str | None:
        if function_name == SqlReferenceKind.REF.function_name:
            generated_name: str = f"{REF_TEST_CTE_PREFIX}{referenced_name}"
            if referenced_name in resolved_chain:
                _ensure_available(generated_name, referenced_name, "ref")
                chain_sql: SqlAnalysisResolvedTestSql = resolved_chain[referenced_name]
                dependency_name: str
                dependency_sql: str
                for dependency_name, dependency_sql in chain_sql.generated_ctes.items():
                    generated_ctes.setdefault(dependency_name, dependency_sql)
                    generated_names.add(dependency_name)
                generated_ctes.setdefault(generated_name, chain_sql.cte_body_sql)
                return generated_name
            if referenced_name in mock_refs:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "ref")
                generated_ctes.setdefault(
                    generated_name, _wrap_mock_body(mock_refs[referenced_name])
                )
                return generated_name
            return None

        if function_name == SqlReferenceKind.SOURCE.function_name:
            generated_name = f"{SOURCE_TEST_CTE_PREFIX}{referenced_name}"
            if referenced_name in mock_sources:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "source")
                generated_ctes.setdefault(
                    generated_name,
                    _wrap_mock_body(mock_sources[referenced_name]),
                )
                return generated_name
            return None

        if function_name == SqlReferenceKind.SEED.function_name:
            generated_name = f"{SEED_TEST_CTE_PREFIX}{referenced_name}"
            if referenced_name in mock_seeds:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "seed")
                generated_ctes.setdefault(
                    generated_name,
                    _wrap_mock_body(mock_seeds[referenced_name]),
                )
                return generated_name
            return None

        if function_name == SqlReferenceKind.DBT_REF.function_name:
            generated_name = f"{DBT_REF_TEST_CTE_PREFIX}{referenced_name}"
            if referenced_name in mock_dbt_refs:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "dbt_ref")
                generated_ctes.setdefault(
                    generated_name,
                    _wrap_mock_body(mock_dbt_refs[referenced_name]),
                )
                return generated_name
            return None

        if function_name == SqlReferenceKind.UDF.function_name:
            target: str | None = function_locations.get(referenced_name)
            if target is not None:
                return target
            return None

        return None

    _replace_relation_markers_in_polyglot_dict(
        parsed_dict,
        polyglot_module=polyglot_module,
        sql_analysis_dialect=None,
        target_for_marker=_target_for_marker,
    )
    transformed_without_with: dict[str, Any] = deepcopy(parsed_dict)
    without_with_select: dict[str, Any] | None = _root_select(transformed_without_with)
    if without_with_select is not None:
        without_with_select["with"] = None
    outer_sql: str | None = _generate_one(
        polyglot_module=polyglot_module, expression=transformed_without_with
    )
    if outer_sql is None:
        return None

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
        )
    return SqlAnalysisResolvedTestSql(
        resolved_sql=f"WITH {', '.join(cte_parts)} {outer_sql}",
        cte_body_sql=cte_body_sql,
        generated_ctes=generated_ctes,
    )


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
            _DEBUG_LOGGER,
            "sql test assembly generation failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if len(generated) != 1:
        return None
    return generated[0]
