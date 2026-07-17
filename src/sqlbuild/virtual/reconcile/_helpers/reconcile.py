"""Virtual reconcile helper logic."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.executor.main._views import refresh_logical_vde_views
from sqlbuild.virtual.reconcile.constants import RECONCILE_REPAIR_VIEW_COMMAND
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.locks._locks import acquire_virtual_environment_lease
from sqlbuild.virtual.state.main.locks._release_lock import release_state_lease
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    ReconcileEventRecord,
    StateLockLease,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType, ReconcileAction, StateOperationStatus


def run_virtual_reconcile(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str | None,
    command: str | None,
    model_name: str | None,
    seed_name: str | None,
    physical_relation_name: str | None,
) -> str:
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    resolved_virtual_environment_name: str | None = virtual_environment_name or resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    active_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    unsuffixed_virtual_environment_name: str | None = None
    if active_target_name is not None:
        unsuffixed_virtual_environment_name = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=active_target_name,
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
    lease: StateLockLease | None = None
    try:
        refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=resolved_virtual_environment_name,
            )
        )
        ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
        seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=resolved_virtual_environment_name,
            )
        )
        seed_ref_map: dict[str, str] = {ref.seed_name: ref.version_hash for ref in seed_refs}
        physical_map: dict[str, PhysicalRelationRecord] = {}
        for ref in refs:
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                connection=state_connection,
                schema=config.schema,
                model_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            if relation is not None:
                physical_map[ref.model_name] = relation
        seed_physical_map: dict[str, PhysicalRelationRecord] = {}
        for ref in seed_refs:
            relation = backend.get_physical_relation_for_artifact(
                connection=state_connection,
                schema=config.schema,
                artifact_type=PhysicalArtifactType.SEED,
                artifact_name=ref.seed_name,
                version_hash=ref.version_hash,
            )
            if relation is not None:
                seed_physical_map[ref.seed_name] = relation

        if command == RECONCILE_REPAIR_VIEW_COMMAND:
            if (model_name is None) == (seed_name is None):
                raise PlannerInputError(
                    "reconcile repair-view requires exactly one of --model or --seed",
                    code="C248",
                )
            lease = acquire_virtual_environment_lease(
                backend=backend,
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=resolved_virtual_environment_name,
                owner_id=f"reconcile:{uuid4()}",
                ttl=timedelta(minutes=10),
            )
            if lease is None:
                raise PlannerInputError(
                    f"virtual environment '{resolved_virtual_environment_name}' is locked",
                    code="S014",
                )
            if seed_name is not None:
                repair_seed_view(
                    graph=graph,
                    adapter=adapter,
                    connection_config=connection_config,
                    virtual_environment_name=resolved_virtual_environment_name,
                    unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
                    seed_name=seed_name,
                    seed_physical_map=seed_physical_map,
                )
                _record_reconcile_event(
                    backend=backend,
                    state_connection=state_connection,
                    schema=config.schema,
                    action=ReconcileAction.REPAIR_VIEW,
                    message=f"repaired seed view for {seed_name}",
                )
                return (
                    "Repair\n"
                    f"  seed    {seed_name}\n"
                    f"  VDE     {resolved_virtual_environment_name}\n"
                    "  action  recreate logical seed view from state\n"
                    "  result  repaired"
                )
            if model_name is None:
                raise PlannerInputError(
                    "reconcile repair-view requires exactly one of --model or --seed",
                    code="C248",
                )
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

        if command == ReconcileAction.ATTACH:
            if model_name is None or physical_relation_name is None:
                raise PlannerInputError(
                    "reconcile attach requires --model and --physical-relation",
                    code="C249",
                )
            lease = acquire_virtual_environment_lease(
                backend=backend,
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=resolved_virtual_environment_name,
                owner_id=f"reconcile:{uuid4()}",
                ttl=timedelta(minutes=10),
            )
            if lease is None:
                raise PlannerInputError(
                    f"virtual environment '{resolved_virtual_environment_name}' is locked",
                    code="S014",
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
            backend.replace_virtual_environment_model_refs(
                connection=state_connection,
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
            seed_ref_map=seed_ref_map,
            seed_physical_map=seed_physical_map,
        )
    finally:
        if lease is not None:
            release_state_lease(
                backend=backend,
                connection=state_connection,
                schema=config.schema,
                lease=lease,
            )
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
    seed_ref_map: dict[str, str],
    seed_physical_map: dict[str, PhysicalRelationRecord],
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
    physical_relation_lookup: RelationLookup = _build_physical_relation_lookup(
        adapter=adapter,
        connection_config=connection_config,
        relations=(*physical_map.values(), *seed_physical_map.values()),
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
        if not physical_relation_lookup.exists(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        ):
            issues.append(f"missing physical relation: {model.name}")
        relation_type: str | None = relation_types.get(model.name)
        if relation_type is None:
            issues.append(f"missing logical target: {model.name}")
        elif normalize_relation_type(relation_type) == RelationType.TABLE:
            issues.append(f"logical target is table: {model.name}")
    if model_name is None:
        for seed in graph.project.seeds:
            if seed.name not in seed_ref_map:
                issues.append(f"missing seed ref: {seed.name}")
                continue
            relation = seed_physical_map.get(seed.name)
            if relation is None:
                issues.append(f"missing tracked physical seed relation: {seed.name}")
                continue
            if not physical_relation_lookup.exists(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
            ):
                issues.append(f"missing physical seed relation: {seed.name}")
            relation_type = relation_types.get(seed.name)
            if relation_type is None:
                issues.append(f"missing logical seed target: {seed.name}")
            elif normalize_relation_type(relation_type) == RelationType.TABLE:
                issues.append(f"logical seed target is table: {seed.name}")
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


def repair_seed_view(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    seed_name: str,
    seed_physical_map: dict[str, PhysicalRelationRecord],
) -> None:
    validate_seed_logical_target_repairable(
        graph=graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        seed_name=seed_name,
    )
    relation: PhysicalRelationRecord | None = seed_physical_map.get(seed_name)
    if relation is None:
        raise PlannerInputError(
            f"missing tracked physical relation for seed '{seed_name}'", code="C251"
        )
    if not physical_relation_exists(
        adapter=adapter, connection_config=connection_config, relation=relation
    ):
        raise PlannerInputError(f"missing physical relation for seed '{seed_name}'", code="C252")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations={},
        seed_physical_relations={seed_name: relation},
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


def validate_seed_logical_target_repairable(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    seed_name: str,
) -> None:
    relation_types: dict[str, str] = list_virtual_relation_types(
        graph=graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
    )
    relation_type: str | None = relation_types.get(seed_name)
    if relation_type is not None and normalize_relation_type(relation_type) == RelationType.TABLE:
        raise PlannerInputError(
            f"logical seed target for '{seed_name}' is a table; repair-view will not overwrite it",
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
        connection=state_connection,
        schema=schema,
        model_name=model_name,
    )
    for candidate in candidates:
        rendered: str = resolve_relation_location_qualified_name(
            adapter=adapter, location=fallback_target(candidate)
        )
        if adapter.relation_names_match(left=rendered, right=physical_relation_name):
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
    existing_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    virtual_environment_name: str,
    model_name: str,
    version_hash: str,
) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
    ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in existing_refs}
    ref_map[model_name] = version_hash
    return tuple(
        VirtualEnvironmentModelRefRecord(
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
    def virtual_schema_for(schema: str | None) -> str | None:
        if schema is None:
            return None
        if unsuffixed_virtual_environment_name == virtual_environment_name:
            return schema
        return f"{schema}__{virtual_environment_name}"

    artifacts: tuple[tuple[str, str | None, str | None, str], ...] = tuple(
        (
            model.name,
            model.destination.database,
            virtual_schema_for(model.destination.schema),
            model.destination.name,
        )
        for model in graph.project.models
    ) + tuple(
        (
            seed.name,
            seed.destination.database,
            virtual_schema_for(seed.destination.schema),
            seed.destination.name,
        )
        for seed in graph.project.seeds
    )
    connection: Any = adapter.connect(connection_config)
    try:
        lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple((database, schema, name) for _, database, schema, name in artifacts),
        )
        result: dict[str, str] = {}
        for artifact_name, database, schema, name in artifacts:
            relation: RelationInfo | None = lookup.get(database=database, schema=schema, name=name)
            if relation is not None:
                result[artifact_name] = relation.relation_type
        return result
    finally:
        adapter.close(connection)


def _build_physical_relation_lookup(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    relations: tuple[PhysicalRelationRecord, ...],
) -> RelationLookup:
    connection: Any = adapter.connect(connection_config)
    try:
        return build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple(
                (relation.database_name, relation.schema_name, relation.relation_name)
                for relation in relations
            ),
        )
    finally:
        adapter.close(connection)


def physical_relation_exists(
    *, adapter: BaseAdapter, connection_config: dict[str, object], relation: PhysicalRelationRecord
) -> bool:
    connection: Any = adapter.connect(connection_config)
    try:
        return adapter.relation_exists(
            connection=connection,
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
        )
    finally:
        adapter.close(connection)


def fallback_target(relation: PhysicalRelationRecord) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=relation.database_name,
        schema=relation.schema_name,
        name=relation.relation_name,
        qualified_name=relation.relation_name,
    )


def _record_reconcile_event(
    *, backend: Any, state_connection: Any, schema: str, action: ReconcileAction, message: str
) -> None:
    backend.create_reconcile_event(
        connection=state_connection,
        schema=schema,
        record=ReconcileEventRecord(
            event_id=uuid4().hex,
            action=action,
            status=StateOperationStatus.SUCCEEDED,
            message=message,
        ),
    )
