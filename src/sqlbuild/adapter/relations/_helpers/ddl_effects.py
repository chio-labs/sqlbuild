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

_LEXEME_ALTERNATIVES: tuple[str, ...] = (
    r"(?P<comment>--[^\n]*|/\*.*?\*/)",
    r"(?P<dollar>\$(?P<tag>[A-Za-z_]*)\$.*?\$(?P=tag)\$)",
    "{literal}",
    r'(?P<quoted>"(?:[^"]|"")*"|`[^`]*`{bracket})',
    r"(?P<unterminated>['\"`]|/\*|\$[A-Za-z_]*\${bracket_open})",
)
_STANDARD_LITERAL: str = r"(?P<literal>'(?:[^']|'')*')"
_BACKSLASH_LITERAL: str = r"(?P<literal>'(?:[^'\\]|\\.|'')*')"
_BRACKET_IDENTIFIER: str = r"|\[[^\]]*\]"
_BRACKET_OPEN: str = r"|\["

_LEXEME_PATTERN: str = "|".join(_LEXEME_ALTERNATIVES)
_LEXERS: tuple[re.Pattern[str], ...] = (
    re.compile(
        _LEXEME_PATTERN.format(literal=_STANDARD_LITERAL, bracket="", bracket_open=""), re.DOTALL
    ),
    re.compile(
        _LEXEME_PATTERN.format(
            literal=_STANDARD_LITERAL, bracket=_BRACKET_IDENTIFIER, bracket_open=_BRACKET_OPEN
        ),
        re.DOTALL,
    ),
    re.compile(
        _LEXEME_PATTERN.format(literal=_BACKSLASH_LITERAL, bracket="", bracket_open=""), re.DOTALL
    ),
    re.compile(
        _LEXEME_PATTERN.format(
            literal=_BACKSLASH_LITERAL, bracket=_BRACKET_IDENTIFIER, bracket_open=_BRACKET_OPEN
        ),
        re.DOTALL,
    ),
)
_UNTERMINATED_MARKER: str = "\x00"
_LEXEME_REPLACEMENTS: dict[str, str] = {
    "comment": " ",
    "dollar": "''",
    "literal": "''",
    "unterminated": _UNTERMINATED_MARKER,
}
_FIRST_WORD: re.Pattern[str] = re.compile(r"[A-Za-z]+")
_IDENTIFIER_PART: str = r'(?:"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][A-Za-z0-9_$]*)'
_QUALIFIED_NAME: str = (
    rf"(?P<name>{_IDENTIFIER_PART}(?:\s*\.\s*{_IDENTIFIER_PART})*)(?P<rest>(?=\s|\()(?s:.*)|$)"
)
_RELATION_KIND: str = (
    r"(?:(?:OR\s+REPLACE|LOCAL|GLOBAL|TEMP|TEMPORARY|TRANSIENT|VOLATILE|SECURE|RECURSIVE|"
    r"MATERIALIZED|EXTERNAL|DYNAMIC|ICEBERG|HYBRID|UNLOGGED|FOREIGN|STREAMING)\s+)*"
    r"(?:TABLE|VIEW)\s+"
)
_CREATE_RELATION: re.Pattern[str] = re.compile(
    rf"^CREATE\s+{_RELATION_KIND}(?:IF\s+NOT\s+EXISTS\s+)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_DROP_RELATION: re.Pattern[str] = re.compile(
    rf"^DROP\s+{_RELATION_KIND}(?:IF\s+EXISTS\s+)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_ALTER_RELATION: re.Pattern[str] = re.compile(
    rf"^ALTER\s+{_RELATION_KIND}(?:IF\s+EXISTS\s+)?{_QUALIFIED_NAME}", re.IGNORECASE
)
_COPY_INTO_RELATION: re.Pattern[str] = re.compile(
    rf"^COPY\s+INTO\s+{_QUALIFIED_NAME}", re.IGNORECASE
)
_SELECT_INTO_RELATION: re.Pattern[str] = re.compile(rf"\bINTO\s+{_QUALIFIED_NAME}", re.IGNORECASE)
_SELECT_INTO_KEYWORD: re.Pattern[str] = re.compile(r"\bINTO\b", re.IGNORECASE)
_SECOND_RELATION: re.Pattern[str] = re.compile(
    rf"^\s+(?:RENAME\s+TO|SWAP\s+WITH)\s+{_QUALIFIED_NAME}", re.IGNORECASE
)
_FOLLOWING_WORDS: dict[re.Pattern[str], re.Pattern[str]] = {
    _CREATE_RELATION: re.compile(
        r"^\s*(?:$|\(|(?:AS|CLONE|LIKE|COPY|USING|COMMENT|CLUSTER|PARTITION|OPTIONS|WITH|"
        r"TBLPROPERTIES|LOCATION|DATA_RETENTION_TIME_IN_DAYS|CHANGE_TRACKING)\b)",
        re.IGNORECASE,
    ),
    _DROP_RELATION: re.compile(r"^\s*(?:CASCADE|RESTRICT|PURGE)?\s*$", re.IGNORECASE),
    _ALTER_RELATION: re.compile(
        r"^\s+(?:ADD|DROP|ALTER|MODIFY|RENAME|SWAP|SET|UNSET|CLUSTER|RECLUSTER|OWNER|"
        r"SUSPEND|RESUME|REFRESH)\b",
        re.IGNORECASE,
    ),
    _COPY_INTO_RELATION: re.compile(r"^\s+FROM\b", re.IGNORECASE),
    _SELECT_INTO_RELATION: re.compile(r"^\s+FROM\b", re.IGNORECASE),
    _SECOND_RELATION: re.compile(r"^\s*$"),
}
_CREATE_SCHEMA_IF_NOT_EXISTS: re.Pattern[str] = re.compile(
    r"^CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+[^\s;]+\s*$", re.IGNORECASE
)
_RELATION_NEUTRAL_OBJECT: re.Pattern[str] = re.compile(
    r"^(?:CREATE|DROP|ALTER)\s+(?:OR\s+REPLACE\s+)?(?:(?:SECURE|TEMP|TEMPORARY|AGGREGATE)\s+)*"
    r"(?:FUNCTION|PROCEDURE|SEQUENCE|STAGE|FILE\s+FORMAT|INDEX|UNIQUE\s+INDEX|WAREHOUSE|MACRO)\b",
    re.IGNORECASE,
)
_RENAMING_ALTER: re.Pattern[str] = re.compile(r"^\s+(?:RENAME\s+TO|SWAP\s+WITH)\b", re.IGNORECASE)
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

    effects: set[StatementMetadataEffect] = {
        _code_effect(code=_code_text(sql=sql, lexer=lexer)) for lexer in _LEXERS
    }
    if len(effects) != 1:
        return _ALL_RELATIONS
    return effects.pop()


def relation_name_key(name: str) -> str:
    """Return the invalidation key for one unquoted or quoted unqualified relation name."""

    return _strip_identifier_quotes(name).casefold()


def qualified_relation_name_key(qualified: str) -> str:
    """Return the invalidation key for the last part of a possibly qualified relation name."""

    return _unqualified_name_key(qualified)


def _code_text(*, sql: str, lexer: re.Pattern[str]) -> str | None:
    if _UNTERMINATED_MARKER in sql:
        return None
    code: str = lexer.sub(_replace_lexeme, sql)
    if _UNTERMINATED_MARKER in code:
        return None
    return code


def _replace_lexeme(match: re.Match[str]) -> str:
    return _LEXEME_REPLACEMENTS.get(match.lastgroup or "", match.group(0))


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
    last: str = parts[-1]
    if last.startswith(BACKTICK):
        return _strip_identifier_quotes(last).rsplit(".", 1)[-1].casefold()
    return relation_name_key(last)


def _strip_identifier_quotes(part: str) -> str:
    if len(part) < QUOTED_IDENTIFIER_MIN_LENGTH:
        return part
    edges: tuple[str, str] = (part[0], part[-1])
    if edges == (DOUBLE_QUOTE, DOUBLE_QUOTE):
        return part[1:-1].replace(DOUBLE_QUOTE * 2, DOUBLE_QUOTE)
    if edges in IDENTIFIER_QUOTE_PAIRS:
        return part[1:-1]
    return part
