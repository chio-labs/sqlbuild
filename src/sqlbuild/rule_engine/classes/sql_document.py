"""Lazy SQL document view for custom rules."""

from typing import Any

from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.rule_engine.constants import AST_CTE_KIND
from sqlbuild.rule_engine.exceptions import RuleUsageError
from sqlbuild.rule_engine.models import SqlNode


class SqlDocument:
    """Lazy authored or expanded SQL view for one compiled model."""

    def __init__(self, *, source: str, dialect: str) -> None:
        self.source: str = source
        self._dialect: str = dialect
        self._ast: Any | None = None

    def polyglot_ast(self) -> Any:
        if self._ast is None:
            polyglot: Any | None = import_polyglot_sql()
            if polyglot is None:
                raise RuleUsageError("rules require the bundled polyglot_sql package")
            self._ast = polyglot.parse_one(self.source, dialect=self._dialect)
        return self._ast

    def nodes(self, *, kind: str) -> tuple[SqlNode, ...]:
        ast: Any = self.polyglot_ast()
        matches: list[Any] = [
            node
            for node in ast.walk()
            if str(getattr(node, "key", "")).casefold() == kind.casefold()
        ]
        if kind.casefold() == AST_CTE_KIND:
            matches.extend(_cte_values(ast))
        return tuple(_source_node(kind=kind, value=node) for node in matches)

    def ctes(self) -> tuple[SqlNode, ...]:
        return self.nodes(kind="CTE")

    def joins(self) -> tuple[SqlNode, ...]:
        return self.nodes(kind="Join")

    def subqueries(self) -> tuple[SqlNode, ...]:
        return self.nodes(kind="Subquery")

    def star_projections(self) -> tuple[SqlNode, ...]:
        return self.nodes(kind="Star")


def _cte_values(ast: Any) -> tuple[object, ...]:
    with_clause: object = getattr(ast, "args", {}).get("with")
    if not isinstance(with_clause, dict):
        return ()
    values: object = with_clause.get("ctes")
    return tuple(values) if isinstance(values, list) else ()


def _source_node(*, kind: str, value: object) -> SqlNode:
    return SqlNode(
        kind=kind,
        line=int(getattr(value, "line", 1) or 1),
        column=int(getattr(value, "column", 1) or 1),
    )
