"""Build dlt destinations from SQLBuild adapter connection config."""

from __future__ import annotations

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.models import DltDestinationConfig


def build_dlt_destination(
    *, adapter_name: str, connection_config: dict[str, object], dataset_name: str | None
) -> DltDestinationConfig:
    """Return a dlt destination object and dataset for a SQLBuild target."""

    try:
        import dlt.destinations as destinations
    except ImportError as error:
        raise DltIntegrationError(
            "This source uses dlt, but dlt is not installed. Install it with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    if adapter_name == BuiltinAdapter.DUCKDB.value:
        return DltDestinationConfig(
            destination=destinations.duckdb(
                credentials=_required_string(
                    connection_config, "database", adapter_name=BuiltinAdapter.DUCKDB.value
                )
            ),
            dataset_name=dataset_name or "main",
        )
    if adapter_name == BuiltinAdapter.MOTHERDUCK.value:
        database: str = _optional_string(connection_config, "database") or ""
        token: str | None = _optional_string(connection_config, "token")
        credentials: str = database if database.startswith("md:") else f"md:{database}"
        if token is not None:
            credentials = f"{credentials}?motherduck_token={token}"
        return DltDestinationConfig(
            destination=destinations.motherduck(credentials=credentials), dataset_name=dataset_name
        )
    if adapter_name == BuiltinAdapter.POSTGRES.value:
        return DltDestinationConfig(
            destination=destinations.postgres(
                credentials=_postgres_connection_string(connection_config)
            ),
            dataset_name=dataset_name,
        )
    raise DltIntegrationError(f"Adapter '{adapter_name}' does not support dlt integration loaders")


def _postgres_connection_string(config: dict[str, object]) -> str:
    host: str = _optional_string(config, "host") or "localhost"
    port: object = config.get("port", 5432)
    user: str = _required_string(config, "user", adapter_name=BuiltinAdapter.POSTGRES.value)
    password: str = _optional_string(config, "password") or ""
    database: str = _optional_string(config, "dbname") or _required_string(
        config, "database", adapter_name=BuiltinAdapter.POSTGRES.value
    )
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


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
