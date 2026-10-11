"""Check SQL syntax natively."""

from __future__ import annotations

import sqlbuild._native as _native


def check_native_sql_syntax(
    *, checks: tuple[tuple[str, dict[str, str] | None], ...], dialect: str | None
) -> bool:
    """Whether every `(sql, placeholders)` parses; raises Python's pre-parse `ValueError`."""

    return _native.check_native_sql_syntax(
        (
            dialect or "generic",
            [(sql, list((placeholders or {}).items())) for sql, placeholders in checks],
        )
    )
