"""SQL hook statement-shape validation entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.sql_hooks._helpers.statement_shape import validate_statement_shape


def validate_sql_hook_statement(*, sql: str, file_path: Path) -> None:
    """Validate the adapter-independent shape of one SQL hook statement."""

    validate_statement_shape(sql=sql, file_path=file_path)
