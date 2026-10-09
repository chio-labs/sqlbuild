"""Check SQL syntax natively for the preview compiler engine."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.project_assembly._helpers.deferrals import record_project_assembly_deferral


def check_native_sql_syntax(
    *, checks: tuple[tuple[str, dict[str, str] | None], ...], dialect: str | None
) -> bool | None:
    """Whether Python's syntax validation accepts every `(sql, placeholders)`; None to check it."""

    valid: bool | None
    deferral: str | None
    valid, deferral = _native.check_native_sql_syntax(
        (
            dialect or "generic",
            [(sql, list((placeholders or {}).items())) for sql, placeholders in checks],
        )
    )
    if valid is None:
        _ = record_project_assembly_deferral(kind=deferral or "unknown")
    return valid
