"""Build ingestr destination URIs from SQLBuild adapter connection config."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from sqlbuild.adapter.types import BuiltinAdapter
from sqlbuild.integrations.ingestr.constants import (
    SQLSERVER_DRIVER_PARAMETER,
    SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER,
)
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError


def build_destination_uri(*, adapter_name: str, connection_config: dict[str, object]) -> str:
    """Return the ingestr destination URI for a SQLBuild connection."""

    if adapter_name == BuiltinAdapter.DUCKDB.value:
        return _duckdb_uri(connection_config)
    if adapter_name == BuiltinAdapter.MOTHERDUCK.value:
        return _motherduck_uri(connection_config)
    if adapter_name == BuiltinAdapter.POSTGRES.value:
        return _postgres_uri(connection_config)
    if adapter_name == BuiltinAdapter.BIGQUERY.value:
        return _bigquery_uri(connection_config)
    if adapter_name == BuiltinAdapter.SNOWFLAKE.value:
        return _snowflake_uri(connection_config)
    if adapter_name == BuiltinAdapter.DATABRICKS.value:
        return _databricks_uri(connection_config)
    if adapter_name == BuiltinAdapter.SQLSERVER.value:
        return _sqlserver_uri(connection_config)
    raise IngestrIntegrationError(
        f"Adapter '{adapter_name}' does not support ingestr integration loaders"
    )


def _required_string(*, config: dict[str, object], key: str, adapter_name: str) -> str:
    value: object | None = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IngestrIntegrationError(
            f"Adapter '{adapter_name}' requires connection.{key} for ingestr integration loaders"
        )
    return value.strip()


def _optional_string(*, config: dict[str, object], key: str) -> str | None:
    value: object | None = config.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _duckdb_uri(config: dict[str, object]) -> str:
    database: str = _required_string(
        config=config, key="database", adapter_name=BuiltinAdapter.DUCKDB.value
    )
    return f"duckdb:///{database}"


def _motherduck_uri(config: dict[str, object]) -> str:
    database: str = _optional_string(config=config, key="database") or ""
    if database.startswith("md:"):
        database = database.removeprefix("md:")
    token: str | None = _optional_string(config=config, key="token")
    query: str = f"?{urlencode({'token': token})}" if token else ""
    return f"motherduck://{quote(database)}{query}"


def _postgres_uri(config: dict[str, object]) -> str:
    host: str = _optional_string(config=config, key="host") or "localhost"
    port: object = config.get("port", 5432)
    user: str = _required_string(
        config=config, key="user", adapter_name=BuiltinAdapter.POSTGRES.value
    )
    password: str = _optional_string(config=config, key="password") or ""
    database: str = _optional_string(config=config, key="dbname") or _required_string(
        config=config, key="database", adapter_name=BuiltinAdapter.POSTGRES.value
    )
    sslmode: str | None = _optional_string(config=config, key="sslmode")
    query: str = f"?{urlencode({'sslmode': sslmode})}" if sslmode else ""
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(database)}{query}"


def _bigquery_uri(config: dict[str, object]) -> str:
    project: str = _optional_string(config=config, key="project") or _required_string(
        config=config, key="database", adapter_name=BuiltinAdapter.BIGQUERY.value
    )
    params: dict[str, str] = {}
    for key in ("location", "credentials_path", "credentials_base64"):
        value: str | None = _optional_string(config=config, key=key)
        if value is not None:
            params[key] = value
    query: str = f"?{urlencode(params)}" if params else ""
    return f"bigquery://{project}{query}"


def _snowflake_uri(config: dict[str, object]) -> str:
    account: str = _required_string(
        config=config, key="account", adapter_name=BuiltinAdapter.SNOWFLAKE.value
    )
    user: str = _required_string(
        config=config, key="user", adapter_name=BuiltinAdapter.SNOWFLAKE.value
    )
    password: str = _optional_string(config=config, key="password") or ""
    database: str = _required_string(
        config=config, key="database", adapter_name=BuiltinAdapter.SNOWFLAKE.value
    )
    schema: str = _required_string(
        config=config, key="schema", adapter_name=BuiltinAdapter.SNOWFLAKE.value
    )
    params: dict[str, str] = {}
    for key in (
        "warehouse",
        "role",
        "token",
        "private_key",
        "private_key_passphrase",
        "authenticator",
    ):
        value: str | None = _optional_string(config=config, key=key)
        if value is not None:
            params[key] = value
    query: str = f"?{urlencode(params)}" if params else ""
    return (
        f"snowflake://{quote(user)}:{quote(password)}@{account}/"
        f"{quote(database)}/{quote(schema)}{query}"
    )


def _databricks_uri(config: dict[str, object]) -> str:
    host: str = _required_string(
        config=config, key="server_hostname", adapter_name=BuiltinAdapter.DATABRICKS.value
    )
    token: str = _required_string(
        config=config, key="token", adapter_name=BuiltinAdapter.DATABRICKS.value
    )
    params: dict[str, str] = {
        "http_path": _required_string(
            config=config, key="http_path", adapter_name=BuiltinAdapter.DATABRICKS.value
        )
    }
    for key in ("catalog", "schema"):
        value: str | None = _optional_string(config=config, key=key)
        if value is not None:
            params[key] = value
    return f"databricks://token:{quote(token)}@{host}?{urlencode(params)}"


def _sqlserver_uri(config: dict[str, object]) -> str:
    host: str = (
        _optional_string(config=config, key="host")
        or _optional_string(config=config, key="server")
        or "localhost"
    )
    port: object = config.get("port", 1433)
    user: str = (
        _optional_string(config=config, key="user")
        or _optional_string(config=config, key="username")
        or "sa"
    )
    password: str = _optional_string(config=config, key="password") or ""
    database: str = (
        _optional_string(config=config, key="database")
        or _optional_string(config=config, key="dbname")
        or "master"
    )
    params: dict[str, str] = {}
    for key in ("driver", "TrustServerCertificate", "Authentication"):
        value: str | None = _optional_string(config=config, key=key)
        if value is not None:
            params[key] = value
    if SQLSERVER_DRIVER_PARAMETER not in params:
        params[SQLSERVER_DRIVER_PARAMETER] = "ODBC Driver 18 for SQL Server"
    if SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER not in params:
        params[SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER] = "yes"
    query: str = f"?{urlencode(params)}" if params else ""
    return f"mssql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(database)}{query}"
