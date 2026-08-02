"""Adapter-aware target namespace validation."""

from __future__ import annotations

from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.expand_template_data import expand_template_data
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import SourceEntry, TargetConfig

_CONNECTION_IDENTITY_KEYS: frozenset[str] = frozenset(
    {"account", "host", "port", "project", "server", "server_hostname", "workspace_url"}
)


def validate_managed_loader_target_isolation(
    *, discovered_inputs: DiscoveredProjectInputs, adapter: BaseAdapter
) -> None:
    """Reject managed loader write namespaces shared by multiple targets."""
    managed_sources: tuple[SourceEntry, ...] = _managed_sources(discovered_inputs)
    if not managed_sources:
        return
    target_names: tuple[str, ...] = tuple(
        sorted(
            set(discovered_inputs.project_config.targets)
            | set(discovered_inputs.local_config.targets)
        )
    )
    namespaces_by_target: dict[str, frozenset[tuple[str | None, str | None]]] = {}
    connections_by_target: dict[str, tuple[tuple[str, str], ...]] = {}
    for target_name in target_names:
        target_config: TargetConfig = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=target_name,
        )
        _, effective_vars, _ = build_effective_runtime_config(
            discovered_inputs=discovered_inputs,
            selected_target=target_name,
        )
        effective_connection: dict[str, object] = build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=target_name,
        )
        connections_by_target[target_name] = _connection_identity(effective_connection)
        namespaces_by_target[target_name] = frozenset(
            _managed_source_namespace(
                source_entry=source_entry,
                target_config=target_config,
                effective_connection=effective_connection,
                effective_vars=effective_vars,
                adapter=adapter,
            )
            for source_entry in managed_sources
        )
    for index, left_target in enumerate(target_names):
        for right_target in target_names[index + 1 :]:
            if connections_by_target[left_target] != connections_by_target[right_target]:
                continue
            shared_namespaces: frozenset[tuple[str | None, str | None]] = (
                namespaces_by_target[left_target] & namespaces_by_target[right_target]
            )
            if not shared_namespaces:
                continue
            database, schema = sorted(shared_namespaces, key=repr)[0]
            raise PlannerInputError(
                "Managed loader write collision: targets "
                f"'{left_target}' and '{right_target}' both resolve to "
                f"database={database!r} schema={schema!r}. Set distinct "
                f"targets.{left_target}.loader_schema and "
                f"targets.{right_target}.loader_schema values.",
                code="S102",
            )


def _connection_identity(connection: dict[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (key, repr(value))
            for key, value in connection.items()
            if key in _CONNECTION_IDENTITY_KEYS
        )
    )


def _managed_sources(discovered_inputs: DiscoveredProjectInputs) -> tuple[SourceEntry, ...]:
    managed_sources: list[SourceEntry] = []
    for source_file in discovered_inputs.source_files:
        for source_entry in source_file.source_entries:
            if source_entry.managed:
                managed_sources.append(source_entry)
    return tuple(managed_sources)


def _managed_source_namespace(
    *,
    source_entry: SourceEntry,
    target_config: TargetConfig,
    effective_connection: dict[str, object],
    effective_vars: dict[str, object],
    adapter: BaseAdapter,
) -> tuple[str | None, str | None]:
    database_value: object = (
        source_entry.database
        or target_config.database
        or effective_connection.get("database")
        or adapter.default_database()
    )
    schema_value: object = (
        source_entry.schema
        or target_config.loader_schema
        or target_config.schema
        or effective_connection.get("schema")
        or adapter.default_schema()
    )
    expanded: object = expand_template_data(
        value={"database": database_value, "schema": schema_value},
        variables=effective_vars,
        context_values={},
        context_label="managed loader target namespace",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
    )
    values: dict[str, object] = cast(dict[str, object], expanded)
    return _optional_string(values["database"]), _optional_string(values["schema"])


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def validate_project_targets(*, adapter_name: str, project: CompiledProject) -> None:
    """Validate compiled model and seed locations for the effective adapter."""

    if adapter_name not in {
        BuiltinAdapter.SNOWFLAKE,
        BuiltinAdapter.BIGQUERY,
        BuiltinAdapter.DATABRICKS,
    }:
        return
    _validate_required_target_parts(
        adapter_name=adapter_name,
        resource_kind="model",
        targets={model.name: model.destination for model in project.models},
    )
    _validate_required_target_parts(
        adapter_name=adapter_name,
        resource_kind="seed",
        targets={seed.name: seed.destination for seed in project.seeds},
    )


def _validate_required_target_parts(
    *,
    adapter_name: str,
    resource_kind: str,
    targets: dict[str, CompiledRelationLocation],
) -> None:
    resource_name: str
    target: CompiledRelationLocation
    for resource_name, target in targets.items():
        missing_parts: list[str] = []
        if target.database is None:
            missing_parts.append("database")
        if target.schema is None:
            missing_parts.append("schema")
        if not missing_parts:
            continue
        missing_text: str = ", ".join(missing_parts)
        raise PlannerInputError(
            f"{adapter_name} execution requires explicit target {missing_text}. "
            f"{resource_kind} '{resource_name}' resolved to "
            f"database={target.database!r} schema={target.schema!r}. "
            "Set them in sqlbuild_project.toml defaults, environment config, or model config.",
            code="S101",
        )
