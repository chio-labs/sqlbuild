"""Shared compile-input projection into a usage-enriched scope index."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.named_declarations.model_schemas import (
    model_schema_scope_usages,
)
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.scopes.main._get_placement_validated_scope_index import (
    get_placement_validated_scope_index,
)
from sqlbuild.compiler.scopes.models import ScopeIndex, UsageRecord


def scope_index_with_compile_usages(*, inputs: CompileInputsView) -> ScopeIndex:
    """Return compile inputs' canonical index with all usage and placement facts."""

    collected_usages: list[UsageRecord] = list(
        model_schema_scope_usages(
            schema_files=inputs.discovered_inputs.model_schema_files,
            resolver=(
                inputs.declaration_scope.resolver if inputs.declaration_scope is not None else None
            ),
        )
    )
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
    return get_placement_validated_scope_index(
        index=inputs.scope_index,
        enforce_placement=inputs.project_config.scopes.enforce_placement,
        compile_usages=tuple(collected_usages),
    )
