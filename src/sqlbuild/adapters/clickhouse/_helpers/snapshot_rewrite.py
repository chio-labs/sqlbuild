"""Stage ClickHouse snapshot statements on a working copy and exchange it into place."""

from __future__ import annotations

import re

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.clickhouse.constants import FRESH_GENERATION_CLAUSE
from sqlbuild.adapters.clickhouse.models import SnapshotWorkspace

_UPDATE_PREFIX: str = "UPDATE "
_TARGET_ALIAS: str = " AS __target SET "
_OFFSET_WINDOW_PATTERN: re.Pattern[str] = re.compile(r"\b(LAG|LEAD)\(([^()]+)\)(\s+OVER\b)")
_ESCAPE_CHARACTER: str = "\\"
_QUOTE_CHARACTERS: str = "'\"`"
_OPEN_PARENTHESIS: str = "("
_CLOSE_PARENTHESIS: str = ")"
_WHERE_KEYWORD: str = " WHERE "
_FROM_KEYWORD: str = " FROM "


def nullable_offset_windows(statements: tuple[str, ...]) -> tuple[str, ...]:
    """Make ``LAG``/``LEAD`` return NULL rather than the type default past the frame edge."""

    return tuple(
        _OFFSET_WINDOW_PATTERN.sub(r"\1(toNullable(\2))\3", statement) for statement in statements
    )


def rewrite_snapshot_statements(
    *, workspace: SnapshotWorkspace, statements: tuple[str, ...]
) -> tuple[str, ...]:
    """Translate statements written against ``workspace.work`` into a staged exchange."""

    rewritten: list[str] = [
        f"DROP TABLE IF EXISTS {workspace.work}",
        f"DROP TABLE IF EXISTS {workspace.rebuild}",
        f"CREATE TABLE {workspace.work} AS {workspace.destination}{FRESH_GENERATION_CLAUSE}",
        f"INSERT INTO {workspace.work} SELECT * FROM {workspace.destination}",
    ]
    statement: str
    for statement in nullable_offset_windows(statements):
        if statement.lstrip().upper().startswith(_UPDATE_PREFIX):
            rewritten.extend(_close_statements(workspace=workspace, statement=statement.strip()))
        else:
            rewritten.append(statement)
    rewritten.extend(
        (
            f"EXCHANGE TABLES {workspace.destination} AND {workspace.work}",
            f"DROP TABLE IF EXISTS {workspace.work}",
        )
    )
    return tuple(rewritten)


def _close_statements(*, workspace: SnapshotWorkspace, statement: str) -> tuple[str, ...]:
    head: str = f"{_UPDATE_PREFIX}{workspace.work}{_TARGET_ALIAS}"
    if not statement.startswith(head):
        raise _unsupported(statement)
    remainder: str = statement[len(head) :]
    assignment_prefix: str = f"{workspace.valid_to_column} = "
    if not remainder.startswith(assignment_prefix):
        raise _unsupported(statement)
    remainder = remainder[len(assignment_prefix) :]
    where_at: int | None = _top_level_keyword(sql=remainder, keyword=_WHERE_KEYWORD)
    if where_at is None:
        raise _unsupported(statement)
    head_sql: str = remainder[:where_at]
    condition: str = remainder[where_at + len(_WHERE_KEYWORD) :]
    from_at: int | None = _top_level_keyword(sql=head_sql, keyword=_FROM_KEYWORD)
    expression: str = head_sql if from_at is None else head_sql[:from_at]
    joined: str = "" if from_at is None else f", {head_sql[from_at + len(_FROM_KEYWORD) :]}"
    valid_to: str = workspace.valid_to_column
    row_hash: str = f"sipHash128(__target.* EXCEPT ({valid_to}))"
    closed_sql: str = (
        f"SELECT {row_hash} AS __sqb_row, min({expression}) AS __sqb_valid_to, "
        f"1 AS __sqb_closed FROM {workspace.work} AS __target{joined} WHERE {condition} "
        "GROUP BY __sqb_row"
    )
    return (
        f"CREATE TABLE {workspace.rebuild} AS {workspace.work}{FRESH_GENERATION_CLAUSE}",
        f"INSERT INTO {workspace.rebuild} SELECT __target.* REPLACE ("
        f"if(__closed.__sqb_closed = 1 AND __target.{valid_to} IS NULL, "
        f"CAST(__closed.__sqb_valid_to, toTypeName(__target.{valid_to})), "
        f"__target.{valid_to}) AS {valid_to}) "
        f"FROM {workspace.work} AS __target LEFT JOIN ({closed_sql}) AS __closed "
        f"ON {row_hash} = __closed.__sqb_row",
        f"EXCHANGE TABLES {workspace.work} AND {workspace.rebuild}",
        f"DROP TABLE {workspace.rebuild}",
    )


def _top_level_keyword(*, sql: str, keyword: str) -> int | None:
    """Return the first position of ``keyword`` outside parentheses and quotes."""

    depth: int = 0
    quote: str | None = None
    index: int = 0
    upper: str = sql.upper()
    while index < len(sql):
        character: str = sql[index]
        if quote is not None:
            if character == _ESCAPE_CHARACTER:
                index += 2
                continue
            if character == quote:
                quote = None
        elif character in _QUOTE_CHARACTERS:
            quote = character
        elif character == _OPEN_PARENTHESIS:
            depth += 1
        elif character == _CLOSE_PARENTHESIS:
            depth -= 1
        elif depth == 0 and upper.startswith(keyword, index):
            return index
        index += 1
    return None


def _unsupported(statement: str) -> AdapterUserError:
    return AdapterUserError(
        message="ClickHouse cannot stage this snapshot statement: " + statement[:200],
        code="A709",
    )
