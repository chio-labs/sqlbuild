"""Build dlt destinations from SQLBuild adapter connection config."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.models import DltDestinationConfig

_DEFAULT_DESTINATION_OPTIONS: dict[str, object] = {"naming_convention": "sql_ci_v1"}
_SQLBUILD_OWNED_DESTINATION_KEYS: frozenset[str] = frozenset(
    {"credentials", "dataset_name", "default_schema_name", "project_id"}
)


def build_dlt_destination(
    *,
    adapter_name: str,
    connection_config: dict[str, object],
    destination_config: dict[str, object] | None = None,
    dataset_name: str | None,
) -> DltDestinationConfig:
    """Return a dlt destination object and dataset for a SQLBuild target."""

    try:
        import dlt.destinations as destinations
    except ImportError as error:
        raise DltIntegrationError(
            "This source uses dlt, but dlt is not installed. Install it with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    destination_options: dict[str, object] = _destination_options(
        adapter_name=adapter_name, destination_config=destination_config or {}
    )
    if adapter_name == BuiltinAdapter.DUCKDB.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.duckdb)(
                credentials=_required_string(
                    connection_config, "database", adapter_name=BuiltinAdapter.DUCKDB.value
                ),
                **destination_options,
            ),
            dataset_name=dataset_name or "main",
        )
    _require_dataset_name(adapter_name=adapter_name, dataset_name=dataset_name)
    if adapter_name == BuiltinAdapter.MOTHERDUCK.value:
        database: str = _optional_string(connection_config, "database") or ""
        token: str | None = _optional_string(connection_config, "token")
        credentials: str = database if database.startswith("md:") else f"md:{database}"
        if token is not None:
            credentials = f"{credentials}?motherduck_token={token}"
        return DltDestinationConfig(
            destination=cast(Any, destinations.motherduck)(
                credentials=credentials, **destination_options
            ),
            dataset_name=dataset_name,
        )
    if adapter_name == BuiltinAdapter.POSTGRES.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.postgres)(
                credentials=_postgres_connection_string(connection_config), **destination_options
            ),
            dataset_name=dataset_name,
        )
    if adapter_name == BuiltinAdapter.SNOWFLAKE.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.snowflake)(
                credentials=_snowflake_credentials(connection_config), **destination_options
            ),
            dataset_name=dataset_name,
        )
    if adapter_name == BuiltinAdapter.BIGQUERY.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.bigquery)(
                **_bigquery_config(connection_config), **destination_options
            ),
            dataset_name=dataset_name,
        )
    if adapter_name == BuiltinAdapter.DATABRICKS.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.databricks)(
                credentials=_databricks_credentials(connection_config), **destination_options
            ),
            dataset_name=dataset_name,
        )
    if adapter_name == BuiltinAdapter.SQLSERVER.value:
        return DltDestinationConfig(
            destination=cast(Any, destinations.mssql)(
                credentials=_sqlserver_credentials(connection_config), **destination_options
            ),
            dataset_name=dataset_name,
        )
    raise DltIntegrationError(f"Adapter '{adapter_name}' does not support dlt integration loaders")


def _destination_options(
    *, adapter_name: str, destination_config: dict[str, object]
) -> dict[str, object]:
    blocked_keys: tuple[str, ...] = tuple(
        key for key in destination_config if key in _SQLBUILD_OWNED_DESTINATION_KEYS
    )
    if blocked_keys:
        blocked: str = ", ".join(sorted(blocked_keys))
        raise DltIntegrationError(
            f"Adapter '{adapter_name}' dlt destination config cannot define SQLBuild-owned key(s): "
            f"{blocked}"
        )
    return {**_DEFAULT_DESTINATION_OPTIONS, **destination_config}


def _postgres_connection_string(config: dict[str, object]) -> str:
    host: str = _optional_string(config, "host") or "localhost"
    port: object = config.get("port", 5432)
    user: str = _required_string(config, "user", adapter_name=BuiltinAdapter.POSTGRES.value)
    password: str = _optional_string(config, "password") or ""
    database: str = _optional_string(config, "dbname") or _required_string(
        config, "database", adapter_name=BuiltinAdapter.POSTGRES.value
    )
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _snowflake_credentials(config: dict[str, object]) -> dict[str, object]:
    account: str = _required_string(config, "account", adapter_name=BuiltinAdapter.SNOWFLAKE.value)
    credentials: dict[str, object] = {
        "account": _snowflake_account(account),
        "host": _snowflake_account(_optional_string(config, "host") or account),
        "user": _required_string(config, "user", adapter_name=BuiltinAdapter.SNOWFLAKE.value),
        "database": _required_string(
            config, "database", adapter_name=BuiltinAdapter.SNOWFLAKE.value
        ),
        "warehouse": _required_string(
            config, "warehouse", adapter_name=BuiltinAdapter.SNOWFLAKE.value
        ),
    }
    _copy_optional(config, credentials, "password")
    _copy_optional(config, credentials, "role")
    _copy_optional(config, credentials, "authenticator")
    _copy_optional(config, credentials, "token")
    return credentials


def _bigquery_config(config: dict[str, object]) -> dict[str, object]:
    options: dict[str, object] = {}
    project_id: str | None = _optional_string(config, "project")
    location: str | None = _optional_string(config, "location")
    if project_id is not None:
        options["project_id"] = project_id
    if location is not None:
        options["location"] = location
    return options


def _snowflake_account(account: str) -> str:
    return account.removesuffix(".snowflakecomputing.com")


def _databricks_credentials(config: dict[str, object]) -> dict[str, object]:
    credentials: dict[str, object] = {
        "server_hostname": _required_string(
            config, "server_hostname", adapter_name=BuiltinAdapter.DATABRICKS.value
        ),
        "http_path": _required_string(
            config, "http_path", adapter_name=BuiltinAdapter.DATABRICKS.value
        ),
        "access_token": _required_string(
            config, "token", adapter_name=BuiltinAdapter.DATABRICKS.value
        ),
    }
    catalog: str | None = _optional_string(config, "catalog")
    if catalog is not None:
        credentials["catalog"] = catalog
    return credentials


def _sqlserver_credentials(config: dict[str, object]) -> dict[str, object]:
    return {
        "host": _optional_string(config, "host") or "localhost",
        "port": config.get("port", 1433),
        "database": _required_string(
            config, "database", adapter_name=BuiltinAdapter.SQLSERVER.value
        ),
        "username": _required_string(config, "user", adapter_name=BuiltinAdapter.SQLSERVER.value),
        "password": _optional_string(config, "password") or "",
        "query": {"TrustServerCertificate": "yes"},
    }


def _require_dataset_name(*, adapter_name: str, dataset_name: str | None) -> None:
    if not isinstance(dataset_name, str) or not dataset_name.strip():
        raise DltIntegrationError(
            f"Adapter '{adapter_name}' requires an explicit dlt source schema for raw landing"
        )


def _copy_optional(source: dict[str, object], destination: dict[str, object], key: str) -> None:
    value: str | None = _optional_string(source, key)
    if value is not None:
        destination[key] = value


def _required_string(config: dict[str, object], key: str, *, adapter_name: str) -> str:
    value: object | None = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DltIntegrationError(
            f"Adapter '{adapter_name}' requires connection.{key} for dlt integration loaders"
        )
    return value.strip()


def _optional_string(config: dict[str, object], key: str) -> str | None:
    value: object | None = config.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
