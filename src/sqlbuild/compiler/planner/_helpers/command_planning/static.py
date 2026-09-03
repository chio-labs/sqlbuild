"""Canonical static planning phases for commands that do not build models."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner._helpers.identity.seed import build_seed_identity
from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    build_planner_relations_context,
    extract_seed_columns,
)
from sqlbuild.compiler.planner._helpers.output.plan_output import (
    build_selected_audit_entries,
    build_selected_test_entries,
    plan_function,
)
from sqlbuild.compiler.planner._helpers.output.strategy import get_materialization_type
from sqlbuild.compiler.planner._helpers.planning.scopes import resolve_planner_scopes
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    DeferralInputs,
    FunctionPlanEntry,
    PlannerPolicies,
    PlannerRelationsContext,
    PlannerScope,
    PlannerSelection,
    PlanOutput,
    PlanWarning,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def resolve_static_command_scope_impl(
    *,
    project: CompiledProject,
    selection: PlannerSelection,
    auto_load_sources: bool = False,
) -> PlannerScope:
    """Resolve command selection through the same canonical selector phase as builds."""

    return resolve_planner_scopes(
        project=project,
        selection=selection,
        policies=PlannerPolicies(auto_load_sources=auto_load_sources),
    ).selected_scope


def resolve_static_relation_context_impl(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    deferral: DeferralInputs | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    relation_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlannerRelationsContext:
    """Resolve canonical locations and source routing without warehouse inventory."""

    return build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=None,
        scope=scope,
        deferral=deferral,
        project_config=project_config,
        local_config=local_config,
        known_source_columns={},
        relation_keys=relation_keys,
    )


def build_audit_command_plan_impl(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
) -> PlanOutput:
    """Project the selected audits from static compile and relation state."""

    model_materializations: dict[str, str] = {
        model.name: get_materialization_type(model).value for model in project.models
    }
    return _base_plan_output(
        project=project,
        scope=scope,
        relations=relations,
        audit_entries=tuple(
            build_selected_audit_entries(
                project=project,
                adapter=adapter,
                scope=scope,
                relations=relations,
                model_materializations=model_materializations,
            )
        ),
    )


def build_test_command_plan_impl(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
) -> PlanOutput:
    """Project selected SQL tests from static compile state."""

    test_entries, warnings = build_selected_test_entries(
        project=project,
        adapter=adapter,
        selected_keys=scope.selected_keys,
    )
    test_keys: frozenset[CompiledObjectKey] = frozenset(entry.key for entry in test_entries)
    function_keys_set: set[CompiledObjectKey] = set()
    for test_entry in test_entries:
        function_keys_set.update(test_entry.function_deps)
    function_keys: frozenset[CompiledObjectKey] = frozenset(function_keys_set)
    function_entries: tuple[FunctionPlanEntry, ...] = tuple(
        plan_function(
            function=function,
            adapter=adapter,
            relations=relations,
            fingerprint_query_sql=build_compiled_function_fingerprint_sql(function),
        )
        for function in project.functions
        if function.key in function_keys
    )
    return _base_plan_output(
        project=project,
        scope=scope,
        relations=relations,
        execution_order=tuple(
            key for key in scope.execution_order if key in scope.selected_keys | test_keys
        ),
        test_entries=tuple(test_entries),
        function_entries=function_entries,
        warnings=tuple(warnings),
    )


def build_seed_command_plan_impl(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    fingerprints: dict[str, Fingerprint] | None = None,
) -> PlanOutput:
    """Project selected direct seed work and canonical identities."""

    existing: dict[str, Fingerprint] = fingerprints or {}
    entries: list[SeedPlanEntry] = []
    for seed in project.seeds:
        if seed.key not in scope.selected_keys:
            continue
        version_hash, metadata_json = build_seed_identity(seed)
        previous: Fingerprint | None = existing.get(seed.name)
        reason: PlanReason = (
            PlanReason.FIRST_RUN
            if previous is None
            else PlanReason.CONFIG_CHANGED
            if previous.version_hash != version_hash
            else PlanReason.NO_CHANGE
        )
        entries.append(
            SeedPlanEntry(
                key=seed.key,
                name=seed.name,
                destination=seed.destination,
                file_path=seed.seed_file.file_path,
                columns=extract_seed_columns(seed),
                csv_settings=seed.schema_entry.csv_settings,
                fingerprint_definition=metadata_json,
                fingerprint_version_hash=version_hash,
                fingerprint_metadata_json=metadata_json,
                reason=reason,
            )
        )
    return _base_plan_output(
        project=project,
        scope=scope,
        relations=relations,
        seed_entries=tuple(entries),
    )


def build_relation_command_plan_impl(
    *, project: CompiledProject, scope: PlannerScope, relations: PlannerRelationsContext
) -> PlanOutput:
    """Project only static relation data for Python checks and scenarios."""

    return _base_plan_output(project=project, scope=scope, relations=relations)


def _base_plan_output(
    *,
    project: CompiledProject,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    execution_order: tuple[CompiledObjectKey, ...] | None = None,
    seed_entries: tuple[SeedPlanEntry, ...] = (),
    function_entries: tuple[FunctionPlanEntry, ...] = (),
    audit_entries: tuple[AuditPlanEntry, ...] = (),
    test_entries: tuple[SqlTestPlanEntry, ...] = (),
    warnings: tuple[PlanWarning, ...] = (),
) -> PlanOutput:
    return PlanOutput(
        execution_order=(
            execution_order
            if execution_order is not None
            else tuple(key for key in scope.execution_order if key in scope.selected_keys)
        ),
        seed_entries=seed_entries,
        function_entries=function_entries,
        audit_entries=audit_entries,
        test_entries=test_entries,
        selected_keys=scope.selected_keys,
        warnings=warnings,
        upstream_deps=scope.upstream_deps,
        downstream_deps=scope.downstream_deps,
        model_locations=relations.model_locations,
        seed_locations=relations.seed_locations,
        function_locations=relations.function_locations,
        source_map=relations.source_map,
        source_read_map=relations.source_read_map,
        hook_functions=project.hook_functions,
    )
