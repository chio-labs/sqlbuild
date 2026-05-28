"""Virtual reconcile helper logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.helpers.relation_type import normalize_relation_type
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.shared.types import RelationType
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.spec.models.environments import resolve_environment_config, resolve_environment_name
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    ReconcileEventRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import ReconcileAction, StateOperationStatus


def run_virtual_reconcile(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str | None,
    command: str | None,
    model_name: str | None,
    physical_relation_name: str | None,
) -> str:
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    resolved_virtual_environment_name: str | None = (
        virtual_environment_name
        or resolve_environment_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            selected_environment=None,
        )
    )
    active_environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=None,
    )
    unsuffixed_virtual_environment_name: str | None = None
    if active_environment_name is not None:
        unsuffixed_virtual_environment_name = resolve_environment_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            environment_name=active_environment_name,
        ).state.unsuffixed_virtual_env
    if resolved_virtual_environment_name is None:
        raise PlannerInputError(
            "reconcile requires --virtual-env or a default environment",
            code="C247",
        )
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=resolved_virtual_environment_name,
        )
        ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
        physical_map: dict[str, PhysicalRelationRecord] = {}
        for ref in refs:
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                state_connection,
                schema=config.schema,
                model_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            if relation is not None:
                physical_map[ref.model_name] = relation

        if command == "repair-view":
            if model_name is None:
                raise PlannerInputError("reconcile repair-view requires --model", code="C248")
            repair_view(
                graph=graph,
                adapter=adapter,
                connection_config=connection_config,
                virtual_environment_name=resolved_virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
                model_name=model_name,
                physical_map=physical_map,
            )
            _record_reconcile_event(
                backend=backend,
                state_connection=state_connection,
                schema=config.schema,
                action=ReconcileAction.REPAIR_VIEW,
                message=f"repaired view for {model_name}",
            )
            return (
                "Repair\n"
                f"  model   {model_name}\n"
                f"  VDE     {resolved_virtual_environment_name}\n"
                "  action  recreate logical view from state\n"
                "  result  repaired"
            )

        if command == "attach":
            if model_name is None or physical_relation_name is None:
                raise PlannerInputError(
                    "reconcile attach requires --model and --physical-relation",
                    code="C249",
                )
            selected_relation: PhysicalRelationRecord = resolve_attach_relation(
                adapter=adapter,
                backend=backend,
                state_connection=state_connection,
                schema=config.schema,
                model_name=model_name,
                physical_relation_name=physical_relation_name,
            )
            validate_logical_target_repairable(
                graph=graph,
                adapter=adapter,
                connection_config=connection_config,
                virtual_environment_name=resolved_virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
                model_name=model_name,
            )
            backend.replace_virtual_environment_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=resolved_virtual_environment_name,
                refs=build_attached_refs(
                    existing_refs=refs,
                    virtual_environment_name=resolved_virtual_environment_name,
                    model_name=model_name,
                    version_hash=selected_relation.version_hash,
                ),
            )
            repair_view(
                graph=graph,
                adapter=adapter,
                connection_config=connection_config,
                virtual_environment_name=resolved_virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
                model_name=model_name,
                physical_map={model_name: selected_relation},
            )
            _record_reconcile_event(
                backend=backend,
                state_connection=state_connection,
                schema=config.schema,
                action=ReconcileAction.ATTACH,
                message=f"attached {model_name} to {physical_relation_name}",
            )
            return (
                "Attach\n"
                f"  model     {model_name}\n"
                f"  VDE       {resolved_virtual_environment_name}\n"
                f"  physical  {physical_relation_name}\n"
                "  result    attached"
            )

        _record_reconcile_event(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            action=ReconcileAction.REPORT,
            message=f"report for {resolved_virtual_environment_name}",
        )
        return build_reconcile_report(
            graph=graph,
            adapter=adapter,
            connection_config=connection_config,
            virtual_environment_name=resolved_virtual_environment_name,
            unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            model_name=model_name,
            ref_map=ref_map,
            physical_map=physical_map,
        )
    finally:
        backend.close(state_connection)


def build_reconcile_report(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    model_name: str | None,
    ref_map: dict[str, str],
    physical_map: dict[str, PhysicalRelationRecord],
) -> str:
    target_names: tuple[str, ...] = (
        (model_name,)
        if model_name is not None
        else tuple(model.name for model in graph.project.models)
    )
    relation_types: dict[str, str] = list_virtual_relation_types(
        graph=graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
    )
    issues: list[str] = []
    for model in graph.project.models:
        if model.name not in target_names:
            continue
        if model.name not in ref_map:
            issues.append(f"missing ref: {model.name}")
            continue
        relation: PhysicalRelationRecord | None = physical_map.get(model.name)
        if relation is None:
            issues.append(f"missing tracked physical relation: {model.name}")
            continue
        if not physical_relation_exists(
            adapter=adapter, connection_config=connection_config, relation=relation
        ):
            issues.append(f"missing physical relation: {model.name}")
        relation_type: str | None = relation_types.get(model.name)
        if relation_type is None:
            issues.append(f"missing logical target: {model.name}")
        elif normalize_relation_type(relation_type) == RelationType.TABLE:
            issues.append(f"logical target is table: {model.name}")
    if not issues:
        return f"Reconcile report for {virtual_environment_name}: no issues."
    return "Reconcile report for " + virtual_environment_name + ":\n- " + "\n- ".join(issues)


def repair_view(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    model_name: str,
    physical_map: dict[str, PhysicalRelationRecord],
) -> None:
    validate_logical_target_repairable(
        graph=graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        model_name=model_name,
    )
    relation: PhysicalRelationRecord | None = physical_map.get(model_name)
    if relation is None:
        raise PlannerInputError(
            f"missing tracked physical relation for '{model_name}'", code="C251"
        )
    if not physical_relation_exists(
        adapter=adapter, connection_config=connection_config, relation=relation
    ):
        raise PlannerInputError(f"missing physical relation for '{model_name}'", code="C252")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations={model_name: relation},
    )


def validate_logical_target_repairable(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    model_name: str,
) -> None:
    relation_types: dict[str, str] = list_virtual_relation_types(
        graph=graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
    )
    relation_type: str | None = relation_types.get(model_name)
    if relation_type is not None and normalize_relation_type(relation_type) == RelationType.TABLE:
        raise PlannerInputError(
            f"logical target for '{model_name}' is a table; repair-view will not overwrite it",
            code="C250",
        )


def resolve_attach_relation(
    *,
    adapter: BaseAdapter,
    backend: Any,
    state_connection: Any,
    schema: str,
    model_name: str,
    physical_relation_name: str,
) -> PhysicalRelationRecord:
    candidates: tuple[PhysicalRelationRecord, ...] = backend.list_physical_relations_for_model(
        state_connection,
        schema=schema,
        model_name=model_name,
    )
    for candidate in candidates:
        rendered: str = resolve_target_qualified_name(
            adapter=adapter, target=fallback_target(candidate)
        )
        if adapter.relation_names_match(rendered, physical_relation_name):
            return candidate
    raise PlannerInputError(
        (
            f"physical relation '{physical_relation_name}' is not a tracked relation "
            f"for '{model_name}'"
        ),
        code="C253",
    )


def build_attached_refs(
    *,
    existing_refs: tuple[VirtualEnvironmentRefRecord, ...],
    virtual_environment_name: str,
    model_name: str,
    version_hash: str,
) -> tuple[VirtualEnvironmentRefRecord, ...]:
    ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in existing_refs}
    ref_map[model_name] = version_hash
    return tuple(
        VirtualEnvironmentRefRecord(
            virtual_environment_name=virtual_environment_name,
            model_name=name,
            version_hash=hash_value,
        )
        for name, hash_value in sorted(ref_map.items())
    )


def list_virtual_relation_types(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
) -> dict[str, str]:
    connection: Any = adapter.connect(connection_config)
    try:
        result: dict[str, str] = {}
        for model in graph.project.models:
            virtual_schema: str | None
            if model.target.schema is None:
                virtual_schema = None
            elif unsuffixed_virtual_environment_name == virtual_environment_name:
                virtual_schema = model.target.schema
            else:
                virtual_schema = f"{model.target.schema}__{virtual_environment_name}"
            relations: tuple[RelationInfo, ...] = adapter.list_relations(
                connection,
                database=model.target.database,
                schemas=((virtual_schema,) if virtual_schema is not None else None),
            )
            for relation in relations:
                if relation.name == model.target.name:
                    result[model.name] = relation.relation_type
                    break
        return result
    finally:
        adapter.close(connection)


def physical_relation_exists(
    *, adapter: BaseAdapter, connection_config: dict[str, object], relation: PhysicalRelationRecord
) -> bool:
    connection: Any = adapter.connect(connection_config)
    try:
        return adapter.relation_exists(
            connection,
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        )
    finally:
        adapter.close(connection)


def fallback_target(relation: PhysicalRelationRecord) -> CompiledRelationTarget:
    return CompiledRelationTarget(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
        qualified_name=relation.relation_name,
    )


def _record_reconcile_event(
    *, backend: Any, state_connection: Any, schema: str, action: ReconcileAction, message: str
) -> None:
    backend.create_reconcile_event(
        state_connection,
        schema=schema,
        record=ReconcileEventRecord(
            event_id=uuid4().hex,
            action=action,
            status=StateOperationStatus.SUCCEEDED,
            message=message,
        ),
    )
