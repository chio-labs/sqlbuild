"""Normalize rendered dbt profile outputs into SQLBuild connection config."""

from __future__ import annotations

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import (
    NormalizedDbtProfileConnection,
    ResolvedDbtProfileOutput,
)


def normalize_dbt_profile_connection(
    *, resolved: ResolvedDbtProfileOutput
) -> NormalizedDbtProfileConnection:
    """Normalize rendered dbt profile output for SQLBuild."""

    adapter_type: str = resolved.adapter_type
    if adapter_type == "duckdb":
        return _normalize_duckdb(resolved=resolved)
    raise DbtProfileError(
        f"dbt profile type '{adapter_type or '<missing>'}' is not supported by SQLBuild "
        "dbt-profile connection resolution yet. Currently supported: duckdb"
    )


def _normalize_duckdb(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    connection: dict[str, object] = {}
    path_value: object | None = output.get("path")
    database_value: object | None = output.get("database")
    database: object = path_value if path_value is not None else database_value
    if database is None:
        database = ":memory:"
    connection["database"] = database
    for key in ("extensions", "settings", "attach"):
        if key in output:
            connection[key] = output[key]
    warnings: list[str] = []
    unsupported_keys: tuple[str, ...] = tuple(
        sorted(
            key
            for key in output
            if key
            in {
                "secrets",
                "filesystems",
                "remote",
                "plugins",
                "module_paths",
                "retries",
                "is_ducklake",
                "use_credential_provider",
                "config_options",
                "external_root",
                "disable_transactions",
                "keep_open",
            }
        )
    )
    if unsupported_keys:
        warnings.append(
            "dbt-duckdb profile fields are not applied by SQLBuild yet: "
            + ", ".join(unsupported_keys)
        )
    schema_value: object | None = output.get("schema")
    target_schema: str | None = schema_value if isinstance(schema_value, str) else None
    database_name: str | None = database_value if isinstance(database_value, str) else None
    return NormalizedDbtProfileConnection(
        adapter="duckdb",
        connection=connection,
        target_schema=target_schema,
        target_database=database_name,
        warnings=tuple(warnings),
    )
