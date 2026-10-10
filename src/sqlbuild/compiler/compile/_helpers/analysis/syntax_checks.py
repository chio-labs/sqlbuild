"""Model placeholders, set operations, and the model and hook SQL Python's assembly validates."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile._helpers.analysis.validation import hook_sql_statements
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.models import CompileModelInput

_HOOK_NAMES: tuple[str, ...] = ("pre_hooks", "post_hooks")
_SET_OPERATION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:UNION|INTERSECT|EXCEPT)\b", re.IGNORECASE
)
_SET_OPERATION_KEYWORDS: tuple[str, ...] = ("UNION", "INTERSECT", "EXCEPT")
_DOTTED_CAPITAL_I: str = "\u0130"


def model_placeholders(model_input: CompileModelInput) -> dict[str, str] | None:
    """Return the model's `@@@name` placeholder defaults as strings, or None."""

    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    return (
        {str(k): str(v) for k, v in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
    )


def model_syntax_checks(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    analysis_model_names: frozenset[str] | None,
    analysis_succeeded: frozenset[str],
) -> tuple[tuple[tuple[str, dict[str, str] | None], ...], ...]:
    """Return each model's `(sql, placeholders)` that assembly would pass to syntax validation."""

    return tuple(
        _syntax_checks(
            model_input=model_input,
            analysis_model_names=analysis_model_names,
            analysis_succeeded=analysis_succeeded,
        )
        for model_input in model_inputs
    )


def _syntax_checks(
    *,
    model_input: CompileModelInput,
    analysis_model_names: frozenset[str] | None,
    analysis_succeeded: frozenset[str],
) -> tuple[tuple[str, dict[str, str] | None], ...]:
    model_name: str = model_input.model_file.file_path.stem
    if not model_input.sql_validation_enabled or (
        analysis_model_names is not None and model_name not in analysis_model_names
    ):
        return ()
    placeholders: dict[str, str] | None = model_placeholders(model_input)
    statements: list[str] = []
    for hook_name in _HOOK_NAMES:
        statements.extend(hook_sql_statements(model_input.config.values.get(hook_name)))
    if model_name not in analysis_succeeded:
        statements.append(
            cursor_intrinsics_analysis_sql(
                sql=model_input.query_sql,
                cursor_type=model_input.config.values.get("cursor_type"),
            )
        )
    return tuple((statement, placeholders) for statement in statements)


def names_set_operation(sql: str) -> bool:
    """Whether the case-insensitive search for `UNION`, `INTERSECT` or `EXCEPT` matches."""

    folded: str = sql.upper().replace(_DOTTED_CAPITAL_I, "I")
    if len(folded) != len(sql):
        return any(keyword in folded for keyword in _SET_OPERATION_KEYWORDS) and (
            _SET_OPERATION_PATTERN.search(sql) is not None
        )
    for keyword in _SET_OPERATION_KEYWORDS:
        offset: int = folded.find(keyword)
        while offset >= 0:
            if _SET_OPERATION_PATTERN.match(sql, offset) is not None:
                return True
            offset = folded.find(keyword, offset + 1)
    return False
