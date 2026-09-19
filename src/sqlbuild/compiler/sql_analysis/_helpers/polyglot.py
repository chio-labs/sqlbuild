"""Required Polyglot import helpers."""

from __future__ import annotations

from typing import Any

import polyglot_sql

from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYZE_QUERY_ENTRY_POINT,
    POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_COUNT,
    POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_INDEX,
    POLYGLOT_COMPLEXITY_GUARD_OPTION,
    POLYGLOT_COMPLEXITY_GUARD_PARAMETER,
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH,
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH_OPTION,
)

_COMPLEXITY_GUARD: dict[str, int] = {
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH_OPTION: POLYGLOT_MAX_FUNCTION_CALL_DEPTH,
}
_GUARDED_ENTRY_POINTS: frozenset[str] = frozenset(
    {
        POLYGLOT_ANALYZE_QUERY_ENTRY_POINT,
        "parse",
        "parse_data_type",
        "parse_one",
        "transpile",
        "validate",
        "validate_with_schema",
    }
)


class _GuardedEntryPoint:
    """One Polyglot entry point with SQLBuild's bounded trusted-SQL budget."""

    def __init__(self, *, name: str, function: Any) -> None:
        self._name: str = name
        self._function: Any = function

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._has_explicit_options_guard(args=args, kwargs=kwargs):
            return self._function(*args, **kwargs)
        guarded_kwargs: dict[str, Any] = {
            POLYGLOT_COMPLEXITY_GUARD_PARAMETER: dict(_COMPLEXITY_GUARD),
            **kwargs,
        }
        return self._function(*args, **guarded_kwargs)

    def _has_explicit_options_guard(self, *, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
        if self._name != POLYGLOT_ANALYZE_QUERY_ENTRY_POINT:
            return False
        options: object = kwargs.get("options")
        if len(args) >= POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_COUNT:
            options = args[POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_INDEX]
        return isinstance(options, dict) and POLYGLOT_COMPLEXITY_GUARD_OPTION in options


class _PolyglotSqlModule:
    """Proxy Polyglot parsing through SQLBuild's trusted-SQL policy."""

    def __getattr__(self, name: str) -> Any:
        attribute: Any = getattr(polyglot_sql, name)
        return (
            _GuardedEntryPoint(name=name, function=attribute)
            if name in _GUARDED_ENTRY_POINTS
            else attribute
        )


_POLYGLOT_SQL_MODULE: _PolyglotSqlModule = _PolyglotSqlModule()


def import_polyglot() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return _POLYGLOT_SQL_MODULE


def import_polyglot_sql() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return import_polyglot()


def is_polyglot_available() -> bool:
    """Return true because Polyglot SQL is a required dependency."""

    return True
