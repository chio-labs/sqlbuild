"""Command construction helpers for ingestr integration loaders."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import cast

from sqlbuild.compiler.compile.main.expand_template_data import expand_template_data
from sqlbuild.integrations.ingestr._helpers.destination import build_destination_uri
from sqlbuild.integrations.ingestr.constants import INGESTR_INTEGRATION_KIND
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.contracts.models import IntegrationLoaderConfig, SourceEntry


def resolve_ingestr_config(
    *, config: IngestrSourceConfig, vars: dict[str, object], environment: str | None, run_id: str
) -> IngestrSourceConfig:
    """Resolve supported templates in ingestr source config values."""

    values: object = expand_template_data(
        value={
            "source_uri": config.source_uri,
            "source_table": config.source_table,
            "strategy": config.strategy,
            "incremental_key": config.incremental_key,
            "primary_key": list(config.primary_key),
            "columns": config.columns,
            "extra_args": list(config.extra_args),
        },
        variables=vars,
        context_values={"environment": environment, "run_id": run_id},
        context_label="ingestr source config",
        allow_context=True,
        preserve_context_tokens=False,
        preserve_unknown_context=True,
    )
    if not isinstance(values, Mapping):
        return config
    resolved_values: Mapping[str, object] = cast(Mapping[str, object], values)
    return replace(
        config,
        source_uri=str(resolved_values["source_uri"]),
        source_table=str(resolved_values["source_table"]),
        strategy=_optional_str(resolved_values.get("strategy")),
        incremental_key=_optional_str(resolved_values.get("incremental_key")),
        primary_key=_string_tuple(resolved_values.get("primary_key")),
        columns=_optional_str(resolved_values.get("columns")),
        extra_args=_string_tuple(resolved_values.get("extra_args")),
    )


def build_ingestr_command(
    *,
    source_entry: SourceEntry,
    adapter_name: str,
    connection_config: dict[str, object],
    destination_table: str,
    vars: dict[str, object],
    environment: str | None,
    run_id: str,
    is_reload: bool,
) -> tuple[str, ...]:
    """Build the ingestr CLI command for one source entry."""

    integration_loader: IntegrationLoaderConfig | None = source_entry.integration_loader
    if integration_loader is None or integration_loader.kind != INGESTR_INTEGRATION_KIND:
        raise IngestrIntegrationError(
            f"Source '{source_entry.name}' does not define ingestr config"
        )
    if not isinstance(integration_loader.config, IngestrSourceConfig):
        raise IngestrIntegrationError(
            f"Source '{source_entry.name}' defines invalid ingestr config"
        )
    config: IngestrSourceConfig = resolve_ingestr_config(
        config=integration_loader.config,
        vars=vars,
        environment=environment,
        run_id=run_id,
    )
    args: list[str] = [
        "ingestr",
        "ingest",
        "--source-uri",
        config.source_uri,
        "--source-table",
        config.source_table,
        "--dest-uri",
        build_destination_uri(adapter_name=adapter_name, connection_config=connection_config),
        "--dest-table",
        destination_table,
        "--yes",
        "--progress",
        "log",
    ]
    if config.strategy is not None:
        args.extend(("--incremental-strategy", config.strategy))
    if config.incremental_key is not None:
        args.extend(("--incremental-key", config.incremental_key))
    for primary_key in config.primary_key:
        args.extend(("--primary-key", primary_key))
    if config.columns is not None:
        args.extend(("--columns", config.columns))
    if is_reload:
        args.append("--full-refresh")
    args.extend(config.extra_args)
    return tuple(args)


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text: str = str(value)
    return text if text else None


def _string_tuple(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    return (str(value),)
