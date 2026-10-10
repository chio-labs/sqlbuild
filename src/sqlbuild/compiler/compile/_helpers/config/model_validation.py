"""Compile-time validation of model config combinations."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.spec.contracts.models import SchemaColumn


def validate_column_migration_config(
    *, config_values: dict[str, object], model_name: str, columns: tuple[SchemaColumn, ...]
) -> None:
    """Validate column-level migrate_from declarations natively as one rename set."""

    problem: _native.NativeConfigError | None = _native.column_migration_problem(
        model_name, config_values, [(column.name, column.migrate_from) for column in columns]
    )
    if problem is not None:
        raise native_config_error(error=problem, values=config_values)
