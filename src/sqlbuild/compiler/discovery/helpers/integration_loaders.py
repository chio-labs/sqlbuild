"""Discovery helpers for declarative integration loaders."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery.exceptions import SourceParseError
from sqlbuild.compiler.discovery.helpers.yml_primitives import (
    optional_non_empty_string,
    require_non_empty_string,
)
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile
from sqlbuild.integrations.dlt.models import DltResourceConfig, DltSourceConfig
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.models.source import IntegrationLoaderConfig, SourceEntry

_ingestr_strategies: frozenset[str] = frozenset(
    {"replace", "append", "merge", "delete+insert", "truncate+insert"}
)


def integration_loader_name(*, kind: str, source_name: str) -> str:
    """Return the generated loader name for a declarative integration loader."""

    if kind == "dlt":
        return source_name
    return f"{kind}__{source_name}"


def build_integration_loader_functions(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Build synthetic loader functions for declarative integration loaders."""

    from sqlbuild.integrations.dlt.main.loaders import build_dlt_loader_functions
    from sqlbuild.integrations.ingestr.main.loaders import build_ingestr_loader_functions

    return build_ingestr_loader_functions(source_files) + build_dlt_loader_functions(source_files)


def parse_dlt_sources(*, payload: dict[str, object], file_path: Path) -> tuple[SourceEntry, ...]:
    """Parse top-level dlt_sources declarations into managed SourceEntry records."""

    raw_groups: object = payload.get("dlt_sources", [])
    if not isinstance(raw_groups, list):
        raise SourceParseError(f"{file_path} dlt_sources must be a list")
    sources: list[SourceEntry] = []
    raw_group: object
    for group_index, raw_group in enumerate(raw_groups):
        if not isinstance(raw_group, dict):
            raise SourceParseError(f"{file_path} dlt_sources must contain only mappings")
        sources.extend(
            _parse_dlt_source_group(
                group=cast(dict[str, object], raw_group),
                file_path=file_path,
                group_index=group_index,
            )
        )
    return tuple(sources)


def parse_source_integration_loader(
    *, entry: dict[str, object], file_path: Path
) -> IntegrationLoaderConfig | None:
    """Parse any source-level integration loader declaration."""

    raw_ingestr: object | None = entry.get("ingestr")
    if raw_ingestr is not None:
        return IntegrationLoaderConfig(
            kind="ingestr",
            config=_parse_ingestr_source_config(raw_config=raw_ingestr, file_path=file_path),
        )
    return None


def _parse_ingestr_source_config(*, raw_config: object, file_path: Path) -> IngestrSourceConfig:
    if not isinstance(raw_config, dict):
        raise SourceParseError(f"{file_path} source 'ingestr' must be a mapping")
    config: dict[str, object] = cast(dict[str, object], raw_config)
    parsed: IngestrSourceConfig = IngestrSourceConfig(
        source_uri=require_non_empty_string(
            entry=config,
            key="source_uri",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        source_table=require_non_empty_string(
            entry=config,
            key="source_table",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        strategy=optional_non_empty_string(
            entry=config,
            key="strategy",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        incremental_key=optional_non_empty_string(
            entry=config,
            key="incremental_key",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        primary_key=_optional_ingestr_primary_key(entry=config, file_path=file_path),
        columns=optional_non_empty_string(
            entry=config,
            key="columns",
            file_path=file_path,
            label="source ingestr",
            error_class=SourceParseError,
        ),
        extra_args=_optional_ingestr_string_tuple(
            entry=config, key="extra_args", file_path=file_path
        ),
    )
    if parsed.strategy is not None and parsed.strategy not in _ingestr_strategies:
        strategies: str = ", ".join(sorted(_ingestr_strategies))
        raise SourceParseError(f"{file_path} source ingestr strategy must be one of: {strategies}")
    return parsed


def _optional_ingestr_primary_key(*, entry: dict[str, object], file_path: Path) -> tuple[str, ...]:
    primary_key: tuple[str, ...] = _optional_ingestr_string_tuple(
        entry=entry, key="primary_key", file_path=file_path
    )
    unique_key: tuple[str, ...] = _optional_ingestr_string_tuple(
        entry=entry, key="unique_key", file_path=file_path
    )
    if primary_key and unique_key:
        raise SourceParseError(
            f"{file_path} source ingestr cannot define both primary_key and unique_key"
        )
    return primary_key or unique_key


def _optional_ingestr_string_tuple(
    *, entry: dict[str, object], key: str, file_path: Path
) -> tuple[str, ...]:
    value: object | None = entry.get(key)
    if value is None:
        return ()
    if isinstance(value, str):
        stripped: str = value.strip()
        if not stripped:
            raise SourceParseError(f"{file_path} source ingestr '{key}' must be non-empty")
        return (stripped,)
    if isinstance(value, list):
        items: list[str] = []
        item: object
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise SourceParseError(
                    f"{file_path} source ingestr '{key}' must contain only non-empty strings"
                )
            items.append(item.strip())
        return tuple(items)
    raise SourceParseError(f"{file_path} source ingestr '{key}' must be a string or list")


def _parse_dlt_source_group(
    *, group: dict[str, object], file_path: Path, group_index: int
) -> tuple[SourceEntry, ...]:
    source_type: str = require_non_empty_string(
        entry=group,
        key="type",
        file_path=file_path,
        label="dlt source",
        error_class=SourceParseError,
    )
    if source_type not in {"sql_database", "rest_api", "filesystem"}:
        raise SourceParseError(
            f"{file_path} dlt source type must be one of: filesystem, rest_api, sql_database"
        )
    raw_config: object | None = group.get("config")
    if not isinstance(raw_config, dict):
        raise SourceParseError(f"{file_path} dlt source config must be a mapping")
    group_config: dict[str, object] = cast(dict[str, object], raw_config)
    destination_config: dict[str, object] = _optional_mapping_value(
        entry=group, key="destination", file_path=file_path, label="dlt source"
    )
    _validate_dlt_destination_config(config=destination_config, file_path=file_path)
    group_schema: str | None = optional_non_empty_string(
        entry=group,
        key="schema",
        file_path=file_path,
        label="dlt source",
        error_class=SourceParseError,
    )
    _validate_dlt_group_config(source_type=source_type, config=group_config, file_path=file_path)
    raw_resources: object = group.get("resources")
    if not isinstance(raw_resources, list) or not raw_resources:
        raise SourceParseError(f"{file_path} dlt source resources must be a non-empty list")
    sources: list[SourceEntry] = []
    raw_resource: object
    for raw_resource in raw_resources:
        if not isinstance(raw_resource, dict):
            raise SourceParseError(f"{file_path} dlt source resources must contain only mappings")
        sources.append(
            _parse_dlt_resource_entry(
                source_type=source_type,
                group_schema=group_schema,
                group_config=group_config,
                destination_config=destination_config,
                resource=cast(dict[str, object], raw_resource),
                file_path=file_path,
                group_index=group_index,
            )
        )
    return tuple(sources)


def _parse_dlt_resource_entry(
    *,
    source_type: str,
    group_schema: str | None,
    group_config: dict[str, object],
    destination_config: dict[str, object],
    resource: dict[str, object],
    file_path: Path,
    group_index: int,
) -> SourceEntry:
    name: str = require_non_empty_string(
        entry=resource,
        key="name",
        file_path=file_path,
        label="dlt resource",
        error_class=SourceParseError,
    )
    if "write_strategy" in resource:
        raise SourceParseError(
            f"{file_path} dlt resource '{name}' must use dlt write_disposition, not write_strategy"
        )
    dlt_name: str = _dlt_resource_name(
        source_type=source_type, resource=resource, file_path=file_path
    )
    write_disposition: object | None = resource.get("write_disposition")
    if write_disposition == "delete_insert":
        raise SourceParseError(
            f"{file_path} dlt resource '{name}' does not support delete_insert; use a Python loader"
        )
    if write_disposition == "merge" and resource.get("primary_key") is None:
        raise SourceParseError(f"{file_path} dlt resource '{name}' merge requires primary_key")
    schema: str | None = (
        optional_non_empty_string(
            entry=resource,
            key="schema",
            file_path=file_path,
            label=f"dlt resource '{name}'",
            error_class=SourceParseError,
        )
        or group_schema
    )
    dlt_resource: DltResourceConfig = DltResourceConfig(
        name=name,
        dlt_name=dlt_name,
        schema=schema,
        raw_config=_raw_dlt_resource_config(source_type=source_type, resource=resource),
        write_disposition=write_disposition,
        primary_key=resource.get("primary_key"),
        merge_key=resource.get("merge_key"),
        incremental=_optional_mapping_value(
            entry=resource, key="incremental", file_path=file_path, label=f"dlt resource '{name}'"
        ),
    )
    return SourceEntry(
        name=name,
        schema=schema,
        table=name,
        managed=True,
        loader=integration_loader_name(kind="dlt", source_name=name),
        integration_loader=IntegrationLoaderConfig(
            kind="dlt",
            config=DltSourceConfig(
                source_type=source_type,
                schema=schema,
                config=group_config,
                destination=destination_config,
                resource=dlt_resource,
                group_index=group_index,
            ),
        ),
    )


def _validate_dlt_group_config(
    *, source_type: str, config: dict[str, object], file_path: Path
) -> None:
    if source_type == "rest_api":
        client: object | None = config.get("client")
        if not isinstance(client, dict):
            raise SourceParseError(f"{file_path} dlt rest_api config requires client.base_url")
        client_config: dict[str, object] = cast(dict[str, object], client)
        if not isinstance(client_config.get("base_url"), str):
            raise SourceParseError(f"{file_path} dlt rest_api config requires client.base_url")
    if source_type == "sql_database" and not isinstance(config.get("credentials"), str):
        raise SourceParseError(f"{file_path} dlt sql_database config requires credentials")
    if source_type == "filesystem" and not isinstance(config.get("bucket_url"), str):
        raise SourceParseError(f"{file_path} dlt filesystem config requires bucket_url")


def _validate_dlt_destination_config(*, config: dict[str, object], file_path: Path) -> None:
    blocked_keys: tuple[str, ...] = ("credentials", "dataset_name", "default_schema_name")
    blocked_key: str
    for blocked_key in blocked_keys:
        if blocked_key in config:
            raise SourceParseError(
                f"{file_path} dlt source destination cannot define '{blocked_key}'"
            )


def _dlt_resource_name(*, source_type: str, resource: dict[str, object], file_path: Path) -> str:
    if source_type == "sql_database":
        return require_non_empty_string(
            entry=resource,
            key="table",
            file_path=file_path,
            label="dlt sql_database resource",
            error_class=SourceParseError,
        )
    if source_type == "rest_api":
        endpoint: object | None = resource.get("endpoint")
        if not isinstance(endpoint, dict):
            raise SourceParseError(f"{file_path} dlt rest_api resource must define endpoint")
        endpoint_config: dict[str, object] = cast(dict[str, object], endpoint)
        endpoint_name: object | None = endpoint_config.get("name")
        if isinstance(endpoint_name, str) and endpoint_name.strip():
            return endpoint_name
        return require_non_empty_string(
            entry=resource,
            key="name",
            file_path=file_path,
            label="dlt rest_api resource",
            error_class=SourceParseError,
        )
    return require_non_empty_string(
        entry=resource,
        key="name",
        file_path=file_path,
        label="dlt filesystem resource",
        error_class=SourceParseError,
    )


def _raw_dlt_resource_config(*, source_type: str, resource: dict[str, object]) -> dict[str, object]:
    excluded: set[str] = {
        "name",
        "table",
        "write_disposition",
        "primary_key",
        "merge_key",
        "incremental",
        "schema",
    }
    if source_type == "rest_api":
        return {"endpoint": resource["endpoint"]}
    return {key: value for key, value in resource.items() if key not in excluded}


def _optional_mapping_value(
    *, entry: dict[str, object], key: str, file_path: Path, label: str
) -> dict[str, object]:
    value: object | None = entry.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SourceParseError(f"{file_path} {label} '{key}' must be a mapping")
    return cast(dict[str, object], value)
