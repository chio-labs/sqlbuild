"""SQL hook statement-shape validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import sqlparse
from sqlparse.sql import Begin, Statement, Token, Values
from sqlparse.tokens import DDL, DML, Comment, Literal

from sqlbuild.compiler.compile.constants import (
    SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN,
    SQL_ARGUMENT_RAW_PARAMETER_PATTERN,
)
from sqlbuild.compiler.discovery.exceptions import SqlHookParseError
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_EXECUTABLE_STATEMENT_KINDS: frozenset[str] = frozenset(
    {
        "alter",
        "analyze",
        "attach",
        "call",
        "command",
        "comment",
        "commit",
        "copy",
        "create",
        "create_procedure",
        "declare",
        "delete",
        "describe",
        "detach",
        "drop",
        "execute",
        "explain",
        "grant",
        "insert",
        "merge",
        "pragma",
        "refresh",
        "revoke",
        "rollback",
        "select",
        "set",
        "show",
        "transaction",
        "truncate",
        "try_catch",
        "union",
        "update",
        "use",
        "vacuum",
        "values",
    }
)
_EXECUTABLE_STATEMENT_KIND_PREFIXES: tuple[str, ...] = ("alter_", "create_", "drop_")
_UNRESOLVED_ARGUMENT_PREFIX: str = "@"
_BATCH_SEPARATOR_PATTERN: re.Pattern[str] = re.compile(
    r"(?im)^[ \t]*go(?:[ \t]+\d+)?[ \t]*(?:--[^\n]*)?$"
)
_PROCEDURAL_BRANCH_LABELS: frozenset[str] = frozenset({"TRY", "CATCH"})
_SET_OPERATORS: tuple[str, ...] = ("UNION", "INTERSECT", "EXCEPT")
_SELECT_ROOT: str = "SELECT"
_IF_ROOT: str = "IF"
_ELSE_ROOT: str = "ELSE"
_BEGIN_BLOCK_ROOT: str = "BEGIN_BLOCK"
_VALUES_ROOT: str = "VALUES"
_BRANCHED_BLOCK_COUNT: int = 2
_NEWLINE: str = "\n"
_COMMAND_STATEMENT_KIND: str = "command"
_RAW_ARGUMENT_STUB: str = "sqlbuild_argument"
_QUOTED_ARGUMENT_STUB: str = "sqlbuild_argument"
_COMPOUND_KIND_SEPARATOR: str = "_"
_STATEMENT_ROOTS: frozenset[str] = frozenset(
    kind.upper() for kind in _EXECUTABLE_STATEMENT_KINDS if _COMPOUND_KIND_SEPARATOR not in kind
) | frozenset(
    {
        "ALTER",
        "BACKUP",
        "CALL",
        "COPY",
        "CREATE",
        "DBCC",
        "DECLARE",
        "DELETE",
        "DENY",
        "DESCRIBE",
        "DROP",
        "DO",
        "EXEC",
        "EXECUTE",
        "EXPLAIN",
        "GRANT",
        _IF_ROOT,
        _ELSE_ROOT,
        "INSERT",
        "MERGE",
        "OPTIMIZE",
        "PRAGMA",
        "PRINT",
        "RAISERROR",
        "REFRESH",
        "RESTORE",
        "SELECT",
        "SET",
        "SHOW",
        "THROW",
        "UPDATE",
        "USE",
        "VACUUM",
        _VALUES_ROOT,
        "WITH",
    }
)
_PRIVILEGE_ROOTS: frozenset[str] = frozenset({"DENY", "GRANT"})
_PRIVILEGE_TARGET_KEYWORD: str = "ON"
_PRIVILEGE_RECIPIENT_KEYWORD: str = "TO"
_PRIVILEGE_RECIPIENT_SEPARATOR: str = ","
_ALLOWED_IF_BRANCH_COMPOSITES: dict[str, frozenset[str]] = {
    "CREATE": frozenset({_SELECT_ROOT}),
    "EXPLAIN": frozenset({_SELECT_ROOT, "DELETE", "INSERT", "MERGE", "UPDATE"}),
    "GRANT": frozenset({_SELECT_ROOT, "DELETE", "EXECUTE", "INSERT", "UPDATE"}),
    "INSERT": frozenset({_SELECT_ROOT}),
    "MERGE": frozenset({"DELETE", "INSERT", "UPDATE"}),
    "WITH": frozenset({_SELECT_ROOT, "DELETE", "INSERT", "MERGE", "UPDATE"}),
}


def validate_statement_shape(*, sql: str, file_path: Path) -> None:
    """Validate the adapter-independent shape of one SQL hook statement."""

    statements: tuple[str, ...] = tuple(sqlparse.split(sql, strip_semicolon=False))
    if len(statements) != 1:
        raise SqlHookParseError(
            f"SQL hook '{file_path}' must define exactly one executable SQL statement"
        )

    statement: str = statements[0].strip()
    statement_without_trivia: str = _strip_leading_trivia(statement)
    if statement_without_trivia.startswith(_UNRESOLVED_ARGUMENT_PREFIX):
        return
    normalized_statement: str = _normalize_unresolved_arguments(statement_without_trivia)
    if not _is_executable_statement(normalized_statement):
        raise SqlHookParseError(f"SQL hook '{file_path}' must define one executable SQL statement")


def _is_executable_statement(sql: str) -> bool:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return _is_supported_dialect_statement(sql)
    try:
        parsed_statements: list[Any] = polyglot_module.parse(sql, dialect="generic")
    except Exception:
        return _is_supported_dialect_statement(sql)
    if len(parsed_statements) != 1:
        return _is_supported_dialect_statement(sql)
    parsed_kind: str = str(getattr(parsed_statements[0], "kind", ""))
    executable_kind: bool = parsed_kind in _EXECUTABLE_STATEMENT_KINDS or parsed_kind.startswith(
        _EXECUTABLE_STATEMENT_KIND_PREFIXES
    )
    return executable_kind and not (
        parsed_kind == _COMMAND_STATEMENT_KIND and _contains_batch_separator(sql=sql)
    )


def _normalize_unresolved_arguments(sql: str) -> str:
    quoted_normalized: str = SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN.sub(
        _QUOTED_ARGUMENT_STUB,
        sql,
    )
    return SQL_ARGUMENT_RAW_PARAMETER_PATTERN.sub(_RAW_ARGUMENT_STUB, quoted_normalized)


def _strip_leading_trivia(sql: str) -> str:
    stripped: str = sql.lstrip()
    while stripped.startswith("--") or stripped.startswith("/*"):
        if stripped.startswith("--"):
            newline: int = stripped.find("\n")
            if newline == -1:
                return ""
            stripped = stripped[newline + 1 :].lstrip()
            continue
        comment_end: int = stripped.find("*/", 2)
        if comment_end == -1:
            return ""
        stripped = stripped[comment_end + 2 :].lstrip()
    return stripped


def _is_supported_dialect_statement(sql: str) -> bool:
    parsed: tuple[Statement, ...] = sqlparse.parse(sql)
    if len(parsed) != 1:
        return False
    tokens: tuple[Token, ...] = tuple(
        token
        for token in parsed[0].tokens
        if not token.is_whitespace and token.ttype not in Comment
    )
    if _contains_batch_separator(statement=parsed[0]):
        return False
    if _is_privilege_statement(statement=parsed[0]):
        return True
    roots: list[str] = []
    set_operator_count: int = 0
    for token in tokens:
        normalized: str = token.normalized.upper()
        if isinstance(token, Begin):
            roots.append(_BEGIN_BLOCK_ROOT)
        elif isinstance(token, Values):
            roots.extend(
                _VALUES_ROOT
                for nested_token in token.flatten()
                if nested_token.normalized.upper() == _VALUES_ROOT
            )
        elif token.ttype in (DDL, DML) or normalized in _STATEMENT_ROOTS:
            roots.append(normalized)
        if normalized.startswith(_SET_OPERATORS):
            set_operator_count += 1
    if not any(isinstance(token, Begin) for token in tokens) and _IF_ROOT not in roots:
        flattened_roots: tuple[str, ...] = _flattened_statement_roots(statement=parsed[0])
        if len(flattened_roots) > len(roots):
            roots = list(flattened_roots)
    return _is_allowed_fallback_root_sequence(
        roots=tuple(roots),
        set_operator_count=set_operator_count,
        tokens=tokens,
    )


def _contains_batch_separator(
    *, sql: str | None = None, statement: Statement | None = None
) -> bool:
    effective_statement: Statement
    if statement is not None:
        effective_statement = statement
    elif sql is not None:
        parsed: tuple[Statement, ...] = sqlparse.parse(sql)
        if len(parsed) != 1:
            return True
        effective_statement = parsed[0]
    else:
        return False
    return (
        _BATCH_SEPARATOR_PATTERN.search(_masked_statement_text(statement=effective_statement))
        is not None
    )


def _flattened_statement_roots(*, statement: Statement) -> tuple[str, ...]:
    roots: list[str] = []
    for token in statement.flatten():
        normalized: str = token.normalized.upper()
        if token.ttype in (DDL, DML) or normalized in _STATEMENT_ROOTS:
            roots.append(normalized)
    return tuple(roots)


def _is_privilege_statement(*, statement: Statement) -> bool:
    tokens: tuple[Token, ...] = tuple(
        token
        for token in statement.flatten()
        if not token.is_whitespace and token.ttype not in Comment
    )
    if not tokens or tokens[0].normalized.upper() not in _PRIVILEGE_ROOTS:
        return False
    normalized_tokens: tuple[str, ...] = tuple(token.normalized.upper() for token in tokens)
    if (
        _PRIVILEGE_TARGET_KEYWORD not in normalized_tokens
        or _PRIVILEGE_RECIPIENT_KEYWORD not in normalized_tokens
    ):
        return False
    target_index: int = normalized_tokens.index(_PRIVILEGE_TARGET_KEYWORD)
    recipient_index: int = normalized_tokens.index(_PRIVILEGE_RECIPIENT_KEYWORD)
    recipient_tokens: tuple[str, ...] = normalized_tokens[recipient_index + 1 :]
    return (
        target_index < recipient_index
        and bool(recipient_tokens)
        and not any(
            token in _STATEMENT_ROOTS
            and index > 0
            and recipient_tokens[index - 1] != _PRIVILEGE_RECIPIENT_SEPARATOR
            for index, token in enumerate(recipient_tokens)
        )
    )


def _masked_statement_text(*, statement: Statement) -> str:
    masked_parts: list[str] = []
    for token in statement.flatten():
        if token.ttype in Comment or token.ttype in Literal:
            masked_parts.append(
                "".join(_NEWLINE if char == _NEWLINE else " " for char in token.value)
            )
        else:
            masked_parts.append(token.value)
    return "".join(masked_parts)


def _is_allowed_fallback_root_sequence(
    *, roots: tuple[str, ...], set_operator_count: int, tokens: tuple[Token, ...]
) -> bool:
    if len(roots) <= 1:
        return bool(roots)
    first_root: str = roots[0]
    if first_root == _SELECT_ROOT:
        return all(root == _SELECT_ROOT for root in roots) and len(roots) == set_operator_count + 1
    if first_root == _IF_ROOT:
        return _is_single_if_statement(roots=roots)
    if first_root == _BEGIN_BLOCK_ROOT:
        return _is_single_branched_block(tokens=tokens)
    return False


def _is_single_if_statement(*, roots: tuple[str, ...]) -> bool:
    branch_roots: tuple[str, ...] = roots[1:]
    if _ELSE_ROOT not in branch_roots:
        return _is_single_if_branch(roots=branch_roots)
    else_index: int = branch_roots.index(_ELSE_ROOT)
    return _is_single_if_branch(roots=branch_roots[:else_index]) and _is_single_if_branch(
        roots=branch_roots[else_index + 1 :]
    )


def _is_single_if_branch(*, roots: tuple[str, ...]) -> bool:
    if len(roots) == 1:
        return True
    if not roots:
        return False
    allowed_tail: frozenset[str] | None = _ALLOWED_IF_BRANCH_COMPOSITES.get(roots[0])
    return allowed_tail is not None and all(root in allowed_tail for root in roots[1:])


def _is_single_branched_block(*, tokens: tuple[Token, ...]) -> bool:
    begin_indexes: tuple[int, ...] = tuple(
        index for index, token in enumerate(tokens) if isinstance(token, Begin)
    )
    if len(begin_indexes) != _BRANCHED_BLOCK_COUNT:
        return False
    first_begin: int = begin_indexes[0]
    second_begin: int = begin_indexes[1]
    between: frozenset[str] = frozenset(
        token.normalized.upper() for token in tokens[first_begin + 1 : second_begin]
    )
    before: frozenset[str] = frozenset(token.normalized.upper() for token in tokens[:first_begin])
    after: frozenset[str] = frozenset(
        token.normalized.upper() for token in tokens[second_begin + 1 :]
    )
    return (
        _PROCEDURAL_BRANCH_LABELS <= between | after or _IF_ROOT in before and _ELSE_ROOT in between
    )
