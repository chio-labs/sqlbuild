"""SQL project variable substitution (@name without parens)."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_scanning import (
    is_identifier_character as _is_identifier_continue,
)
from sqlbuild.compiler.compile.helpers.sql_scanning import (
    is_identifier_start as _is_identifier_start,
)
from sqlbuild.compiler.compile.helpers.sql_scanning import (
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
)
from sqlbuild.compiler.compile.models import LoadedMacro

_CONTEXT: str = "Variable substitution"
_VAR_PATTERN: re.Pattern[str] = re.compile(r"@([a-zA-Z_][a-zA-Z0-9_]*)")


def validate_var_macro_collision(
    *,
    effective_vars: dict[str, str],
    loaded_macros: dict[str, LoadedMacro],
) -> None:
    """Raise if any project var name collides with a macro name."""

    collisions: set[str] = set(effective_vars) & set(loaded_macros)
    if collisions:
        names: str = ", ".join(sorted(collisions))
        raise CompileInputError(
            f"project variable names collide with macro names: {names}. "
            f"Rename the variable or macro to avoid ambiguity."
        )


def substitute_sql_vars(
    *,
    sql: str,
    file_path: Path,
    effective_vars: dict[str, str],
) -> str:
    """Replace bare @name references with project variable values.

    Only replaces @name that is NOT followed by '(' (those are macro calls).
    Skips quoted strings and comments.
    """

    if "@" not in sql or not effective_vars:
        return sql

    parts: list[str] = []
    cursor: int = 0
    while cursor < len(sql):
        character: str = sql[cursor]
        if character in {"'", '"', "`"}:
            end: int = skip_quoted_text(sql=sql, start=cursor, context=_CONTEXT)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if sql.startswith("--", cursor):
            end = skip_line_comment(sql=sql, start=cursor)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if sql.startswith("/*", cursor):
            end = skip_block_comment(sql=sql, start=cursor, context=_CONTEXT)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if character == "@" and cursor + 1 < len(sql) and _is_identifier_start(sql[cursor + 1]):
            name_start: int = cursor + 1
            name_end: int = name_start + 1
            while name_end < len(sql) and _is_identifier_continue(sql[name_end]):
                name_end += 1
            paren_check: int = name_end
            while paren_check < len(sql) and sql[paren_check].isspace():
                paren_check += 1
            if paren_check < len(sql) and sql[paren_check] == "(":
                parts.append(sql[cursor:name_end])
                cursor = name_end
                continue
            var_name: str = sql[name_start:name_end]
            if var_name not in effective_vars:
                raise CompileInputError(
                    f"unknown project variable '@{var_name}' in '{file_path}'. "
                    f"Available vars: {', '.join(sorted(effective_vars)) or 'none'}"
                )
            parts.append(effective_vars[var_name])
            cursor = name_end
            continue
        parts.append(character)
        cursor += 1
    return "".join(parts)
