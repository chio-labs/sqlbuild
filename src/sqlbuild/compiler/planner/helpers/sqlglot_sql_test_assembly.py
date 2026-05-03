"""Optional SQLGlot-backed SQL-native test assembly helpers."""

from __future__ import annotations

from collections import OrderedDict
from importlib import import_module
from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.planner.models import SqlglotResolvedTestSql


def try_resolve_test_model_sql_with_sqlglot(
    *,
    query_sql: str,
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    helper_ctes: tuple[CompileSqlTestCte, ...],
    resolved_chain: dict[str, SqlglotResolvedTestSql],
    reachable_mocks: set[str],
    file_label: str,
) -> SqlglotResolvedTestSql | None:
    """Return SQLGlot-backed readable test SQL or None on import/parse failure."""

    try:
        sqlglot_module: Any = import_module("sqlglot")
        expressions_module: Any = import_module("sqlglot.expressions")
    except ModuleNotFoundError:
        return None

    try:
        parsed: Any = sqlglot_module.parse_one(query_sql)
    except Exception:
        return None

    generated_ctes: OrderedDict[str, str] = OrderedDict()
    generated_names: set[str] = set()
    table_type: type[Any] = expressions_module.Table
    anonymous_type: type[Any] = expressions_module.Anonymous
    identifier_type: type[Any] = expressions_module.Identifier

    existing_with: Any | None = parsed.args.get("with_")
    if existing_with is not None:
        cte: Any
        for cte in existing_with.expressions:
            alias: Any | None = getattr(cte, "alias", None)
            if alias is None:
                continue
            alias_name: str = alias if isinstance(alias, str) else str(alias)
            generated_names.add(alias_name)

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

        if function_name == "__ref":
            generated_name: str = f"__ref__{referenced_name}"
            if referenced_name in resolved_chain:
                _ensure_available(generated_name, referenced_name, "ref")
                chain_sql: SqlglotResolvedTestSql = resolved_chain[referenced_name]
                dependency_name: str
                dependency_sql: str
                for dependency_name, dependency_sql in chain_sql.generated_ctes.items():
                    generated_ctes.setdefault(dependency_name, dependency_sql)
                    generated_names.add(dependency_name)
                generated_ctes.setdefault(generated_name, chain_sql.cte_body_sql)
                table.set("this", identifier_type(this=generated_name, quoted=False))
                return table
            if referenced_name in mock_refs:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "ref")
                generated_ctes.setdefault(
                    generated_name, _wrap_mock_body(mock_refs[referenced_name])
                )
                table.set("this", identifier_type(this=generated_name, quoted=False))
                return table
            return table

        if function_name == "__source":
            generated_name = f"__source__{referenced_name}"
            if referenced_name in mock_sources:
                reachable_mocks.add(referenced_name)
                _ensure_available(generated_name, referenced_name, "source")
                generated_ctes.setdefault(
                    generated_name,
                    _wrap_mock_body(mock_sources[referenced_name]),
                )
                table.set("this", identifier_type(this=generated_name, quoted=False))
                return table
            return table

        return table

    transformed: Any = parsed.transform(_replace_table)
    transformed_with: Any | None = transformed.args.get("with_")
    transformed_without_with: Any = transformed.copy()
    transformed_without_with.set("with_", None)
    outer_sql: str = transformed_without_with.sql(pretty=False)

    cte_parts: list[str] = [f"{name} AS ({sql})" for name, sql in generated_ctes.items()]
    if transformed_with is not None:
        cte: Any
        for cte in transformed_with.expressions:
            cte_parts.append(cte.sql(pretty=False))
    cte_body_sql: str = transformed.sql(pretty=False)
    if not cte_parts:
        return SqlglotResolvedTestSql(
            resolved_sql=cte_body_sql,
            cte_body_sql=cte_body_sql,
            generated_ctes=generated_ctes,
        )
    return SqlglotResolvedTestSql(
        resolved_sql=f"WITH {', '.join(cte_parts)} {outer_sql}",
        cte_body_sql=cte_body_sql,
        generated_ctes=generated_ctes,
    )
