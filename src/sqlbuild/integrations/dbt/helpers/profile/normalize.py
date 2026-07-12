"""Normalize rendered dbt profile outputs into SQLBuild connection config."""

from __future__ import annotations

from sqlbuild.adapter.shared.types import BuiltinAdapter
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
    try:
        builtin_adapter: BuiltinAdapter = BuiltinAdapter(adapter_type)
    except ValueError as exc:
        raise DbtProfileError(
            f"dbt profile type '{adapter_type or '<missing>'}' is not supported by SQLBuild "
            "dbt-profile connection resolution yet. Currently supported: "
            "bigquery, databricks, duckdb, postgres, snowflake, sqlserver"
        ) from exc
    match builtin_adapter:
        case BuiltinAdapter.DUCKDB:
            return _normalize_duckdb(resolved=resolved)
        case BuiltinAdapter.POSTGRES:
            return _normalize_postgres(resolved=resolved)
        case BuiltinAdapter.SNOWFLAKE:
            return _normalize_snowflake(resolved=resolved)
        case BuiltinAdapter.BIGQUERY:
            return _normalize_bigquery(resolved=resolved)
        case BuiltinAdapter.DATABRICKS:
            return _normalize_databricks(resolved=resolved)
        case BuiltinAdapter.SQLSERVER:
            return _normalize_sqlserver(resolved=resolved)
        case BuiltinAdapter.MOTHERDUCK:
            raise DbtProfileError(
                "dbt profile type 'motherduck' is not supported directly. Use a dbt-duckdb "
                "profile with a MotherDuck path after SQLBuild MotherDuck profile support lands."
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
        adapter=BuiltinAdapter.DUCKDB.value,
        connection=connection,
        target_schema=target_schema,
        target_database=database_name,
        warnings=tuple(warnings),
    )


def _normalize_postgres(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    connection: dict[str, object] = _copy_present(
        output=output,
        keys=(
            "host",
            "port",
            "user",
            "connect_timeout",
            "role",
            "keepalives_idle",
            "sslmode",
            "sslcert",
            "sslkey",
            "sslrootcert",
            "application_name",
        ),
    )
    database: object | None = output.get("dbname", output.get("database"))
    password: object | None = output.get("pass", output.get("password"))
    if database is not None:
        connection["dbname"] = database
    if password is not None:
        connection["password"] = password
    target_schema: str | None = _string_or_none(output.get("schema"))
    return NormalizedDbtProfileConnection(
        adapter=BuiltinAdapter.POSTGRES.value,
        connection=connection,
        target_schema=target_schema,
        target_database=None,
    )


def _normalize_snowflake(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    connection: dict[str, object] = dict(output)
    connection.pop("type", None)
    connection.pop("threads", None)
    return NormalizedDbtProfileConnection(
        adapter=BuiltinAdapter.SNOWFLAKE.value,
        connection=connection,
        target_schema=_string_or_none(output.get("schema")),
        target_database=_string_or_none(output.get("database")),
    )


def _normalize_bigquery(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    method: str | None = _string_or_none(output.get("method"))
    if method in {"oauth-secrets", "service-account-json", "external-oauth-wif"}:
        raise DbtProfileError(
            "dbt BigQuery profile method "
            f"'{method}' is not supported by SQLBuild dbt-profile normalization yet. "
            "Supported methods: oauth, service-account"
        )
    project: object | None = output.get("project", output.get("database"))
    connection: dict[str, object] = {}
    if project is not None:
        connection["project"] = project
    if "location" in output:
        connection["location"] = output["location"]
    if "keyfile" in output:
        connection["credentials_path"] = output["keyfile"]
    if method is not None and method not in {"oauth", "service-account"}:
        raise DbtProfileError(
            "dbt BigQuery profile method "
            f"'{method}' is not supported by SQLBuild dbt-profile normalization yet. "
            "Supported methods: oauth, service-account"
        )
    return NormalizedDbtProfileConnection(
        adapter=BuiltinAdapter.BIGQUERY.value,
        connection=connection,
        target_schema=_string_or_none(output.get("dataset", output.get("schema"))),
        target_database=_string_or_none(project),
    )


def _normalize_databricks(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    unsupported_auth_keys: tuple[str, ...] = tuple(
        sorted(
            key
            for key in (
                "client_id",
                "client_secret",
                "azure_client_id",
                "azure_client_secret",
                "oauth_redirect_url",
                "oauth_scopes",
            )
            if output.get(key) is not None
        )
    )
    auth_type: str | None = _string_or_none(output.get("auth_type"))
    if auth_type is not None and auth_type != "pat":
        raise DbtProfileError(
            "dbt Databricks profile auth_type "
            f"'{auth_type}' is not supported by SQLBuild dbt-profile normalization yet. "
            "Supported auth: personal access token"
        )
    if unsupported_auth_keys:
        raise DbtProfileError(
            "dbt Databricks OAuth/Azure profile fields are not supported by SQLBuild "
            "dbt-profile normalization yet: " + ", ".join(unsupported_auth_keys)
        )
    connection: dict[str, object] = {}
    if "host" in output:
        connection["server_hostname"] = output["host"]
    if "http_path" in output:
        connection["http_path"] = output["http_path"]
    if "token" in output:
        connection["token"] = output["token"]
    catalog: object | None = output.get("catalog", output.get("database"))
    if catalog is None:
        catalog = "hive_metastore"
    connection["catalog"] = catalog
    if "schema" in output:
        connection["schema"] = output["schema"]
    return NormalizedDbtProfileConnection(
        adapter=BuiltinAdapter.DATABRICKS.value,
        connection=connection,
        target_schema=_string_or_none(output.get("schema")),
        target_database=_string_or_none(catalog),
    )


def _normalize_sqlserver(*, resolved: ResolvedDbtProfileOutput) -> NormalizedDbtProfileConnection:
    output: dict[str, object] = dict(resolved.output)
    if output.get("windows_login") is True or output.get("trusted_connection") is True:
        raise DbtProfileError(
            "dbt SQL Server Windows authentication is not supported by SQLBuild "
            "dbt-profile normalization yet"
        )
    authentication: str | None = _string_or_none(output.get("authentication", output.get("auth")))
    if authentication is not None and authentication.lower() != "sql":
        raise DbtProfileError(
            "dbt SQL Server authentication mode "
            f"'{authentication}' is not supported by SQLBuild dbt-profile normalization yet. "
            "Supported authentication: sql"
        )
    connection: dict[str, object] = {}
    host: object | None = output.get("server", output.get("host"))
    user: object | None = output.get("UID", output.get("user", output.get("username")))
    password: object | None = output.get("PWD", output.get("password", output.get("pass")))
    for key, value in (
        ("host", host),
        ("port", output.get("port")),
        ("user", user),
        ("password", password),
        ("database", output.get("database")),
    ):
        if value is not None:
            connection[key] = value
    return NormalizedDbtProfileConnection(
        adapter=BuiltinAdapter.SQLSERVER.value,
        connection=connection,
        target_schema=_string_or_none(output.get("schema")),
        target_database=None,
    )


def _copy_present(*, output: dict[str, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {key: output[key] for key in keys if key in output}


def _string_or_none(value: object | None) -> str | None:
    return value if isinstance(value, str) and value else None
