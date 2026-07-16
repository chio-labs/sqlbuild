"""dlt source construction helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from sqlbuild.integrations.dlt.constants import (
    DLT_FILESYSTEM_READER_CSV,
    DLT_FILESYSTEM_READER_JSONL,
    DLT_FILESYSTEM_READER_PARQUET,
    DLT_SOURCE_TYPE_FILESYSTEM,
    DLT_SOURCE_TYPE_REST_API,
    DLT_SOURCE_TYPE_SQL_DATABASE,
)
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.models import DltSourceConfig


def build_dlt_source(config: DltSourceConfig) -> Any:
    """Build a dlt source/resource for one declarative SQLBuild resource."""

    if config.source_type == DLT_SOURCE_TYPE_SQL_DATABASE:
        return _build_sql_database_source(config)
    if config.source_type == DLT_SOURCE_TYPE_REST_API:
        return _build_rest_api_source(config)
    if config.source_type == DLT_SOURCE_TYPE_FILESYSTEM:
        return _build_filesystem_resource(config)
    raise DltIntegrationError(f"Unsupported dlt source type '{config.source_type}'")


def _build_sql_database_source(config: DltSourceConfig) -> Any:
    try:
        from dlt.sources.sql_database import sql_database
    except ImportError as error:
        raise DltIntegrationError(
            "dlt sql_database sources require dlt SQL database dependencies. Install with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    source_config: dict[str, object] = deepcopy(config.config)
    source_config["table_names"] = [config.resource.dlt_name]
    source_factory: Any = sql_database
    source: Any = source_factory(**cast(Any, source_config))
    return source.with_resources(config.resource.dlt_name)


def _build_rest_api_source(config: DltSourceConfig) -> Any:
    try:
        from dlt.sources.rest_api import rest_api_source
    except ImportError as error:
        raise DltIntegrationError(
            "dlt rest_api sources require dlt. Install with: pip install 'sqlbuild[dlt]'"
        ) from error

    source_config: dict[str, object] = deepcopy(config.config)
    source_config["resources"] = [_rest_resource_config(config)]
    source: Any = rest_api_source(cast(Any, source_config))
    return source.with_resources(config.resource.dlt_name)


def _build_filesystem_resource(config: DltSourceConfig) -> Any:
    try:
        from dlt.sources.filesystem import filesystem, read_csv, read_jsonl, read_parquet
    except ImportError as error:
        raise DltIntegrationError(
            "dlt filesystem sources require dlt filesystem dependencies. Install with: "
            "pip install 'sqlbuild[dlt]'"
        ) from error

    reader: object | None = config.resource.raw_config.get("reader")
    if not isinstance(reader, str):
        raise DltIntegrationError(
            f"dlt filesystem source '{config.resource.name}' must define reader"
        )
    source_config: dict[str, object] = deepcopy(config.config)
    filesystem_factory: Any = filesystem
    resource: Any = filesystem_factory(**cast(Any, source_config))
    if reader == DLT_FILESYSTEM_READER_CSV:
        return resource | read_csv().with_name(config.resource.dlt_name)
    if reader == DLT_FILESYSTEM_READER_JSONL:
        return resource | read_jsonl().with_name(config.resource.dlt_name)
    if reader == DLT_FILESYSTEM_READER_PARQUET:
        return resource | read_parquet().with_name(config.resource.dlt_name)
    raise DltIntegrationError(
        f"dlt filesystem source '{config.resource.name}' reader must be one of: csv, jsonl, parquet"
    )


def _rest_resource_config(config: DltSourceConfig) -> dict[str, object]:
    resource_config: dict[str, object] = deepcopy(config.resource.raw_config)
    resource_config["name"] = config.resource.dlt_name
    if config.resource.write_disposition is not None:
        resource_config["write_disposition"] = config.resource.write_disposition
    if config.resource.primary_key is not None:
        resource_config["primary_key"] = config.resource.primary_key
    if config.resource.merge_key is not None:
        resource_config["merge_key"] = config.resource.merge_key
    return resource_config
