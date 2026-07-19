"""Public helpers for logical VDE view refreshes."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.virtual.executor._helpers.environment_views import write_vde_views_from_records
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def refresh_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None = None,
    physical_relations: dict[str, PhysicalRelationRecord],
    seed_physical_relations: dict[str, PhysicalRelationRecord] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
) -> None:
    """Create or replace logical VDE views from tracked physical relations."""

    write_vde_views_from_records(
        project=project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations=physical_relations,
        seed_physical_relations=seed_physical_relations or {},
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )
