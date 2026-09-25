"""Effective target identifier semantics for native schema validation."""

from typing import Any

from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_SNOWFLAKE: str = "snowflake"
_PARAMETER: str = "QUOTED_IDENTIFIERS_IGNORE_CASE"
_QUOTED_IDENTIFIER: str = "QUOTED_IDENTIFIER"
_UPPERCASE: dict[int, int] = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def ignores_quoted_case(*, connection: dict[str, object], dialect: str | None) -> bool:
    """Read only an explicitly enabled setting from the resolved connection."""
    if dialect != _SNOWFLAKE:
        return False
    parameters: object = connection.get("session_parameters")
    if not isinstance(parameters, dict):
        return False
    return any(
        str(key).upper() == _PARAMETER and value is True for key, value in parameters.items()
    )


def fold_quoted_identifiers(*, sql: str, dialect: str | None) -> str:
    """Fold identifier tokens without touching literals, comments, or span lengths."""
    module: Any = import_polyglot_sql()
    tokens: list[dict[str, Any]] = module.tokenize(sql, dialect=dialect)
    pieces: list[str] = []
    previous: int = 0
    for token in tokens:
        if token["token_type"] != _QUOTED_IDENTIFIER:
            continue
        start: int = token["span"]["start"]
        end: int = token["span"]["end"]
        pieces.extend((sql[previous:start], sql[start:end].translate(_UPPERCASE)))
        previous = end
    pieces.append(sql[previous:])
    return "".join(pieces)
