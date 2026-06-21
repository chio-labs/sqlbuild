"""Configuration resolution helpers for declarative dlt sources."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from sqlbuild.compiler.compile.main.expand_template_data import expand_template_data
from sqlbuild.integrations.dlt.models import DltResourceConfig, DltSourceConfig


def resolve_dlt_config(
    *, config: DltSourceConfig, vars: dict[str, object], environment: str | None, run_id: str
) -> DltSourceConfig:
    """Resolve supported templates in dlt source config values."""

    values: object = expand_template_data(
        {
            "config": config.config,
            "destination": config.destination,
            "schema": config.schema,
            "resource": config.resource.raw_config,
            "resource_schema": config.resource.schema,
            "write_disposition": config.resource.write_disposition,
            "primary_key": config.resource.primary_key,
            "merge_key": config.resource.merge_key,
            "incremental": config.resource.incremental,
        },
        variables=vars,
        context_values={"environment": environment, "run_id": run_id},
        context_label="dlt source config",
        allow_context=True,
        preserve_context_tokens=False,
        preserve_unknown_context=True,
    )
    if not isinstance(values, dict):
        return config
    resolved_values: dict[str, object] = cast(dict[str, object], values)
    resolved_resource: DltResourceConfig = replace(
        config.resource,
        schema=_optional_string(resolved_values.get("resource_schema")),
        raw_config=_mapping(resolved_values.get("resource")),
        write_disposition=resolved_values.get("write_disposition"),
        primary_key=resolved_values.get("primary_key"),
        merge_key=resolved_values.get("merge_key"),
        incremental=_mapping(resolved_values.get("incremental")),
    )
    return replace(
        config,
        schema=_optional_string(resolved_values.get("schema")),
        config=_mapping(resolved_values.get("config")),
        destination=_mapping(resolved_values.get("destination")),
        resource=resolved_resource,
    )


def _mapping(value: object | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return dict(cast(dict[str, object], value))


def _optional_string(value: object | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
