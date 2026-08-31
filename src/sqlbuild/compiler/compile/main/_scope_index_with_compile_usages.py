"""Shared compile-input projection into a usage-enriched scope index."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.scopes.main._get_placement_validated_scope_index import (
    get_placement_validated_scope_index,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ScopeIndex,
    UsageRecord,
)


def scope_index_with_compile_usages(*, inputs: CompileProjectInputs) -> ScopeIndex:
    """Return compile inputs' canonical index with all usage and placement facts."""

    collected_usages: list[UsageRecord] = []
    for model_input in inputs.model_inputs:
        collected_usages.extend(model_input.macro_usages)
        collected_usages.extend(model_input.declaration_usages)
    for source_input in inputs.source_inputs:
        collected_usages.extend(source_input.declaration_usages)
    for function_input in inputs.sql_function_inputs:
        collected_usages.extend(function_input.declaration_usages)
    for audit_input in inputs.audit_inputs:
        collected_usages.extend(audit_input.declaration_usages)
    for test_input in inputs.test_inputs:
        collected_usages.extend(test_input.declaration_usages)
    for scenario_input in inputs.scenario_inputs:
        collected_usages.extend(scenario_input.declaration_usages)
    usages: tuple[UsageRecord, ...] = tuple(dict.fromkeys(collected_usages))
    dependencies: dict[DeclarationIdentity, list[DeclarationIdentity]] = {}
    for usage in usages:
        if isinstance(usage.consumer, DeclarationIdentity):
            dependencies.setdefault(usage.consumer, []).append(usage.declaration)
    declarations: tuple[DeclarationRecord, ...] = tuple(
        replace(
            record,
            macro=replace(
                record.macro,
                dependencies=tuple(
                    dict.fromkeys(
                        (*record.macro.dependencies, *dependencies.get(record.identity, ()))
                    )
                ),
            ),
        )
        if record.macro is not None
        else record
        for record in inputs.scope_index.declarations
    )
    index: ScopeIndex = replace(
        inputs.scope_index,
        declarations=declarations,
        usages=tuple(dict.fromkeys((*inputs.scope_index.usages, *usages))),
        completeness=replace(
            inputs.scope_index.completeness,
            runtime_usage=True,
            promotion_impact=True,
        ),
    )
    return get_placement_validated_scope_index(
        index=index,
        enforce_placement=inputs.project_config.scopes.enforce_placement,
    )
