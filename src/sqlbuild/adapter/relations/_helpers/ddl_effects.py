"""Classify executed SQL by its effect on cached relation existence and columns."""

from __future__ import annotations

import re

from sqlbuild.adapter.relations.constants import (
    DOUBLE_QUOTE,
    IDENTIFIER_QUOTE_PAIRS,
    QUOTED_IDENTIFIER_MIN_LENGTH,
    STATEMENT_SEPARATOR,
)
from sqlbuild.adapter.relations.models import StatementMetadataEffect

_LINE_COMMENT: re.Pattern[str] = re.compile(r"--[^\n]*")
_BLOCK_COMMENT: re.Pattern[str] = re.compile(r"/\*.*?\*/", re.DOTALL)
_FIRST_WORD: re.Pattern[str] = re.compile(r"[A-Za-z]+")
_IDENTIFIER_PART: str = r'(?:"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]|[A-Za-z0-9_$@#-]+)'
_QUALIFIED_NAME: str = rf"(?P<name>{_IDENTIFIER_PART}(?:\s*\.\s*{_IDENTIFIER_PART})*)"
_RELATION_KIND: str = (
    r"(?:(?:OR\s+REPLACE|LOCAL|GLOBAL|TEMP|TEMPORARY|TRANSIENT|VOLATILE|SECURE|RECURSIVE|"
    r"MATERIALIZED|EXTERNAL|DYNAMIC|ICEBERG|HYBRID|UNLOGGED|FOREIGN|STREAMING)\s+)*"
    r"(?:TABLE|VIEW)\s+"
)
_CREATE_RELATION: re.Pattern[str] = re.compile(
    rf"^CREATE\s+{_RELATION_KIND}(?:IF\s+NOT\s+EXISTS\s+)?{_QUALIFIED_NAME}",
    re.IGNORECASE,
)
_DROP_RELATION: re.Pattern[str] = re.compile(
    rf"^DROP\s+{_RELATION_KIND}(?:IF\s+EXISTS\s+)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_ALTER_RELATION: re.Pattern[str] = re.compile(
    rf"^ALTER\s+{_RELATION_KIND}(?:IF\s+EXISTS\s+)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_ALTER_SECOND_RELATION: re.Pattern[str] = re.compile(
    rf"\b(?:RENAME\s+TO|SWAP\s+WITH)\s+{_QUALIFIED_NAME}", re.IGNORECASE
)
_SELECT_INTO_RELATION: re.Pattern[str] = re.compile(rf"\bINTO\s+{_QUALIFIED_NAME}", re.IGNORECASE)
_COPY_INTO_RELATION: re.Pattern[str] = re.compile(
    rf"^COPY\s+INTO\s+{_QUALIFIED_NAME}", re.IGNORECASE
)
_CREATE_SCHEMA_IF_NOT_EXISTS: re.Pattern[str] = re.compile(
    r"^CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+[^\s;]+\s*;?\s*$", re.IGNORECASE
)
_RELATION_NEUTRAL_OBJECT: re.Pattern[str] = re.compile(
    r"^(?:CREATE|DROP|ALTER)\s+(?:OR\s+REPLACE\s+)?(?:(?:SECURE|TEMP|TEMPORARY|AGGREGATE)\s+)*"
    r"(?:FUNCTION|PROCEDURE|SEQUENCE|STAGE|FILE\s+FORMAT|INDEX|UNIQUE\s+INDEX|WAREHOUSE|MACRO)\b",
    re.IGNORECASE,
)
_QUERY_STATEMENTS: frozenset[str] = frozenset({"SELECT", "WITH"})
_READ_OR_DATA_STATEMENTS: frozenset[str] = frozenset(
    {
        "VALUES",
        "SHOW",
        "DESCRIBE",
        "DESC",
        "EXPLAIN",
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "TRUNCATE",
        "BEGIN",
        "START",
        "SAVEPOINT",
        "RELEASE",
        "SET",
        "UNSET",
        "GRANT",
        "REVOKE",
        "COMMENT",
        "PUT",
        "GET",
        "LIST",
        "LS",
        "REMOVE",
        "RM",
        "ANALYZE",
    }
)
_TRANSACTION_END_STATEMENTS: frozenset[str] = frozenset({"COMMIT", "ROLLBACK", "END", "ABORT"})
_RELATION_DDL_STATEMENTS: frozenset[str] = frozenset({"CREATE", "DROP", "ALTER", "COPY"})


_NO_EFFECT: StatementMetadataEffect = StatementMetadataEffect()
_ALL_RELATIONS: StatementMetadataEffect = StatementMetadataEffect(invalidates_all=True)
_TRANSACTION_END: StatementMetadataEffect = StatementMetadataEffect(ends_transaction=True)


def statement_metadata_effect(sql: str) -> StatementMetadataEffect:
    """Return which cached relation names ``sql`` may have changed."""

    statement: str = (
        _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql))
        .strip()
        .rstrip(STATEMENT_SEPARATOR)
        .strip()
        .lstrip("(")
    )
    first: re.Match[str] | None = _FIRST_WORD.match(statement)
    if first is None or STATEMENT_SEPARATOR in statement:
        return _ALL_RELATIONS
    keyword: str = first.group(0).upper()
    if keyword in _QUERY_STATEMENTS:
        return _select_into_effect(statement=statement)
    if keyword in _READ_OR_DATA_STATEMENTS:
        return _NO_EFFECT
    if keyword in _TRANSACTION_END_STATEMENTS:
        return _TRANSACTION_END
    if keyword not in _RELATION_DDL_STATEMENTS:
        return _ALL_RELATIONS
    if (
        _CREATE_SCHEMA_IF_NOT_EXISTS.match(statement) is not None
        or _RELATION_NEUTRAL_OBJECT.match(statement) is not None
    ):
        return _NO_EFFECT
    return _relation_ddl_effect(statement=statement)


def relation_name_key(name: str) -> str:
    """Return the invalidation key for one unquoted or quoted unqualified relation name."""

    return _strip_identifier_quotes(name).casefold()


def _select_into_effect(*, statement: str) -> StatementMetadataEffect:
    created: re.Match[str] | None = _SELECT_INTO_RELATION.search(statement)
    if created is None:
        return _NO_EFFECT
    return StatementMetadataEffect(
        relation_names=frozenset({_unqualified_name_key(created.group("name"))})
    )


def _relation_ddl_effect(*, statement: str) -> StatementMetadataEffect:
    pattern: re.Pattern[str]
    for pattern in (_CREATE_RELATION, _DROP_RELATION, _ALTER_RELATION, _COPY_INTO_RELATION):
        match: re.Match[str] | None = pattern.match(statement)
        if match is None:
            continue
        names: set[str] = {_unqualified_name_key(match.group("name"))}
        if pattern is _ALTER_RELATION:
            names.update(
                _unqualified_name_key(second.group("name"))
                for second in _ALTER_SECOND_RELATION.finditer(statement, match.end())
            )
        return StatementMetadataEffect(relation_names=frozenset(names))
    return _ALL_RELATIONS


def _unqualified_name_key(qualified: str) -> str:
    parts: list[str] = re.findall(_IDENTIFIER_PART, qualified)
    last: str = _strip_identifier_quotes(parts[-1])
    return last.rsplit(".", 1)[-1].casefold()


def _strip_identifier_quotes(part: str) -> str:
    if len(part) < QUOTED_IDENTIFIER_MIN_LENGTH:
        return part
    edges: tuple[str, str] = (part[0], part[-1])
    if edges == (DOUBLE_QUOTE, DOUBLE_QUOTE):
        return part[1:-1].replace(DOUBLE_QUOTE * 2, DOUBLE_QUOTE)
    if edges in IDENTIFIER_QUOTE_PAIRS:
        return part[1:-1]
    return part
