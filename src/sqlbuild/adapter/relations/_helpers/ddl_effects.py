"""Classify executed SQL by its effect on cached relation existence and columns."""

from __future__ import annotations

import re

from sqlbuild.adapter.relations.constants import (
    BACKTICK,
    DOUBLE_QUOTE,
    IDENTIFIER_QUOTE_PAIRS,
    QUOTED_IDENTIFIER_MIN_LENGTH,
    STATEMENT_SEPARATOR,
)
from sqlbuild.adapter.relations.models import StatementMetadataEffect

_LEXEME_START: re.Pattern[str] = re.compile(r"--|/\*|['\"`$\[]")
_BACKSLASH_LITERAL_STOP: re.Pattern[str] = re.compile(r"[\\']")
_DOLLAR_TAG: re.Pattern[str] = re.compile(r"\$[A-Za-z_]*+\$")
_LINE_COMMENT_START: str = "--"
_BLOCK_COMMENT_START: str = "/*"
_BLOCK_COMMENT_END: str = "*/"
_SINGLE_QUOTE: str = "'"
_BACKSLASH: str = "\\"
_DOLLAR: str = "$"
_OPEN_BRACKET: str = "["
_CLOSE_BRACKET: str = "]"
_NEWLINE: str = "\n"
_EMPTY_LITERAL: str = "''"
_COMMENT_REPLACEMENT: str = " "
_FIRST_WORD: re.Pattern[str] = re.compile(r"[A-Za-z]+")
_IDENTIFIER_PART: str = r'(?:"(?:[^"]|"")*+"|`[^`]*+`|\[[^\]]*+\]|[A-Za-z0-9_][A-Za-z0-9_$]*+)'
_QUALIFIED_NAME: str = (
    rf"(?P<name>{_IDENTIFIER_PART}(?:\s*+\.\s*+{_IDENTIFIER_PART})*+)"
    r"(?P<rest>(?=\s|\()(?s:.*)|$)"
)
_LOOSE_IDENTIFIER_PART: str = r'(?:"(?:[^"]|"")*+"|`[^`]*+`|\[[^\]]*+\]|[A-Za-z0-9_$-]++)'
_LOOSE_QUALIFIED_NAME: re.Pattern[str] = re.compile(
    rf"^\s*+{_LOOSE_IDENTIFIER_PART}(?:\s*+\.\s*+{_LOOSE_IDENTIFIER_PART})*+\s*+$"
)
_RELATION_KIND: str = (
    r"(?:(?:OR\s++REPLACE|LOCAL|GLOBAL|TEMP|TEMPORARY|TRANSIENT|VOLATILE|SECURE|RECURSIVE|"
    r"MATERIALIZED|EXTERNAL|DYNAMIC|ICEBERG|HYBRID|UNLOGGED|FOREIGN|STREAMING)\s++)*+"
    r"(?:TABLE|VIEW)\s++"
)
_CREATE_RELATION: re.Pattern[str] = re.compile(
    rf"^CREATE\s++{_RELATION_KIND}(?:IF\s++NOT\s++EXISTS\s++)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_DROP_RELATION: re.Pattern[str] = re.compile(
    rf"^DROP\s++{_RELATION_KIND}(?:IF\s++EXISTS\s++)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_ALTER_RELATION: re.Pattern[str] = re.compile(
    rf"^ALTER\s++{_RELATION_KIND}(?:IF\s++EXISTS\s++)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_COPY_INTO_RELATION: re.Pattern[str] = re.compile(
    rf"^COPY\s++INTO\s++{_QUALIFIED_NAME}", re.IGNORECASE
)
_SELECT_INTO_RELATION: re.Pattern[str] = re.compile(rf"\bINTO\s++{_QUALIFIED_NAME}", re.IGNORECASE)
_SELECT_INTO_KEYWORD: re.Pattern[str] = re.compile(r"\bINTO\b", re.IGNORECASE)
_SECOND_RELATION: re.Pattern[str] = re.compile(
    rf"^\s++(?:RENAME\s++TO|SWAP\s++WITH)\s++{_QUALIFIED_NAME}", re.IGNORECASE
)
_FOLLOWING_WORDS: dict[re.Pattern[str], re.Pattern[str]] = {
    _CREATE_RELATION: re.compile(
        r"^\s*+(?:$|\(|(?:AS|CLONE|SHALLOW|DEEP|LIKE|COPY|USING|COMMENT|CLUSTER|PARTITION|OPTIONS|WITH|"
        r"TBLPROPERTIES|LOCATION|DATA_RETENTION_TIME_IN_DAYS|CHANGE_TRACKING)\b)",
        re.IGNORECASE,
    ),
    _DROP_RELATION: re.compile(r"^\s*+(?:CASCADE|RESTRICT|PURGE)?+\s*+$", re.IGNORECASE),
    _ALTER_RELATION: re.compile(
        r"^\s++(?:ADD|DROP|ALTER|MODIFY|RENAME|SWAP|SET|UNSET|CLUSTER|RECLUSTER|OWNER|"
        r"SUSPEND|RESUME|REFRESH)\b",
        re.IGNORECASE,
    ),
    _COPY_INTO_RELATION: re.compile(r"^\s++FROM\b", re.IGNORECASE),
    _SELECT_INTO_RELATION: re.compile(r"^\s++FROM\b", re.IGNORECASE),
    _SECOND_RELATION: re.compile(r"^\s*+$"),
}
_CREATE_SCHEMA_IF_NOT_EXISTS: re.Pattern[str] = re.compile(
    r"^CREATE\s++SCHEMA\s++IF\s++NOT\s++EXISTS\s++[^\s;]++\s*+$", re.IGNORECASE
)
_RELATION_NEUTRAL_OBJECT: re.Pattern[str] = re.compile(
    r"^(?:CREATE|DROP|ALTER)\s++(?:OR\s++REPLACE\s++)?(?:(?:SECURE|TEMP|TEMPORARY|AGGREGATE)\s++)*+"
    r"(?:FUNCTION|PROCEDURE|SEQUENCE|STAGE|FILE\s++FORMAT|INDEX|UNIQUE\s++INDEX|WAREHOUSE|MACRO)\b",
    re.IGNORECASE,
)
_RENAMING_ALTER: re.Pattern[str] = re.compile(
    r"^\s++(?:RENAME\s++TO|SWAP\s++WITH)\b", re.IGNORECASE
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
    """Return which cached relation names ``sql`` may have changed; ambiguity changes all."""

    backslash_modes: tuple[bool, ...] = (False, True) if _BACKSLASH in sql else (False,)
    bracket_modes: tuple[bool, ...] = (False, True) if _OPEN_BRACKET in sql else (False,)
    effects: set[StatementMetadataEffect] = set()
    backslash_escapes: bool
    for backslash_escapes in backslash_modes:
        effects.update(
            _code_effect(
                code=_code_text(
                    sql=sql, backslash_escapes=backslash_escapes, bracket_identifiers=brackets
                )
            )
            for brackets in bracket_modes
        )
    if len(effects) != 1:
        return _ALL_RELATIONS
    return effects.pop()


def relation_name_key(name: str) -> str:
    """Return the invalidation key for one unquoted or quoted unqualified relation name."""

    return _strip_identifier_quotes(name).casefold()


def qualified_relation_name_key(qualified: str) -> str | None:
    """Return the key for the last part of a qualified name, or None when it cannot be parsed."""

    if _LOOSE_QUALIFIED_NAME.match(qualified) is None:
        return None
    parts: list[str] = re.findall(_LOOSE_IDENTIFIER_PART, qualified)
    return _part_name_key(parts[-1])


def _code_text(*, sql: str, backslash_escapes: bool, bracket_identifiers: bool) -> str | None:
    pieces: list[str] = []
    position: int = 0
    while True:
        start: re.Match[str] | None = _LEXEME_START.search(sql, position)
        if start is None:
            pieces.append(sql[position:])
            return "".join(pieces)
        pieces.append(sql[position : start.start()])
        lexeme: tuple[str, int] | None = _read_lexeme(
            sql=sql,
            start=start,
            backslash_escapes=backslash_escapes,
            bracket_identifiers=bracket_identifiers,
        )
        if lexeme is None:
            return None
        pieces.append(lexeme[0])
        position = lexeme[1]


def _read_lexeme(
    *, sql: str, start: re.Match[str], backslash_escapes: bool, bracket_identifiers: bool
) -> tuple[str, int] | None:
    token: str = start.group(0)
    begin: int = start.start()
    if token == _LINE_COMMENT_START:
        line_end: int = sql.find(_NEWLINE, begin)
        return _COMMENT_REPLACEMENT, (len(sql) if line_end < 0 else line_end)
    if token == _BLOCK_COMMENT_START:
        return _closed(
            text=_COMMENT_REPLACEMENT, end=sql.find(_BLOCK_COMMENT_END, begin + 2), width=2
        )
    if token == _SINGLE_QUOTE:
        return _closed(
            text=_EMPTY_LITERAL,
            end=_literal_end(sql=sql, begin=begin, backslash_escapes=backslash_escapes),
            width=1,
        )
    if token == _DOLLAR:
        return _dollar_lexeme(sql=sql, begin=begin)
    if token == _OPEN_BRACKET and not bracket_identifiers:
        return token, begin + 1
    closing: str = _CLOSE_BRACKET if token == _OPEN_BRACKET else token
    end: int = _quoted_end(sql=sql, begin=begin, quote=closing)
    if end < 0:
        return None
    return sql[begin : end + 1], end + 1


def _closed(*, text: str, end: int, width: int) -> tuple[str, int] | None:
    if end < 0:
        return None
    return text, end + width


def _dollar_lexeme(*, sql: str, begin: int) -> tuple[str, int] | None:
    tag: re.Match[str] | None = _DOLLAR_TAG.match(sql, begin)
    if tag is None:
        return _DOLLAR, begin + 1
    return _closed(
        text=_EMPTY_LITERAL, end=sql.find(tag.group(0), tag.end()), width=len(tag.group(0))
    )


def _literal_end(*, sql: str, begin: int, backslash_escapes: bool) -> int:
    position: int = begin + 1
    while True:
        stop: int = _literal_stop(sql=sql, position=position, backslash_escapes=backslash_escapes)
        if stop < 0:
            return stop
        if sql[stop] == _BACKSLASH:
            position = stop + 2
            continue
        if sql.startswith(_EMPTY_LITERAL, stop):
            position = stop + 2
            continue
        return stop


def _literal_stop(*, sql: str, position: int, backslash_escapes: bool) -> int:
    if not backslash_escapes:
        return sql.find(_SINGLE_QUOTE, position)
    stop: re.Match[str] | None = _BACKSLASH_LITERAL_STOP.search(sql, position)
    return -1 if stop is None else stop.start()


def _quoted_end(*, sql: str, begin: int, quote: str) -> int:
    position: int = begin + 1
    while True:
        end: int = sql.find(quote, position)
        if end < 0 or quote == _CLOSE_BRACKET or not sql.startswith(quote * 2, end):
            return end
        position = end + 2


def _code_effect(*, code: str | None) -> StatementMetadataEffect:
    if code is None:
        return _ALL_RELATIONS
    statement: str = code.strip().rstrip(STATEMENT_SEPARATOR).strip().lstrip("(")
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


def _select_into_effect(*, statement: str) -> StatementMetadataEffect:
    if _SELECT_INTO_KEYWORD.search(statement) is None:
        return _NO_EFFECT
    created: re.Match[str] | None = _SELECT_INTO_RELATION.search(statement)
    names: frozenset[str] | None = _unambiguous_names(pattern=_SELECT_INTO_RELATION, match=created)
    if names is None:
        return _ALL_RELATIONS
    return StatementMetadataEffect(relation_names=names)


def _relation_ddl_effect(*, statement: str) -> StatementMetadataEffect:
    pattern: re.Pattern[str]
    for pattern in (_CREATE_RELATION, _DROP_RELATION, _ALTER_RELATION, _COPY_INTO_RELATION):
        match: re.Match[str] | None = pattern.match(statement)
        names: frozenset[str] | None = _unambiguous_names(pattern=pattern, match=match)
        if names is not None:
            return StatementMetadataEffect(relation_names=names)
    return _ALL_RELATIONS


def _unambiguous_names(
    *, pattern: re.Pattern[str], match: re.Match[str] | None
) -> frozenset[str] | None:
    if match is None:
        return None
    rest: str = match.group("rest")
    if _FOLLOWING_WORDS[pattern].match(rest) is None:
        return None
    name: str = _unqualified_name_key(match.group("name"))
    if pattern is not _ALTER_RELATION or _RENAMING_ALTER.match(rest) is None:
        return frozenset({name})
    second: frozenset[str] | None = _unambiguous_names(
        pattern=_SECOND_RELATION, match=_SECOND_RELATION.match(rest)
    )
    if second is None:
        return None
    return frozenset({name, *second})


def _unqualified_name_key(qualified: str) -> str:
    parts: list[str] = re.findall(_IDENTIFIER_PART, qualified)
    return _part_name_key(parts[-1])


def _part_name_key(part: str) -> str:
    if part.startswith(BACKTICK):
        return _strip_identifier_quotes(part).rsplit(".", 1)[-1].casefold()
    return relation_name_key(part)


def _strip_identifier_quotes(part: str) -> str:
    if len(part) < QUOTED_IDENTIFIER_MIN_LENGTH:
        return part
    edges: tuple[str, str] = (part[0], part[-1])
    if edges == (DOUBLE_QUOTE, DOUBLE_QUOTE):
        return part[1:-1].replace(DOUBLE_QUOTE * 2, DOUBLE_QUOTE)
    if edges in IDENTIFIER_QUOTE_PAIRS:
        return part[1:-1]
    return part
