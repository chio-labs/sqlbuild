"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import partial
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile._helpers.analysis.cache import (
    build_analysis_cache_context,
    build_compact_analysis_cache_plan,
    compact_analysis_batch_response_writer,
    model_analysis_cache_key,
    model_analysis_output_signature,
    read_compact_analysis_cache_candidate,
    read_model_analyses,
    record_analysis_cache_metrics,
    write_model_analyses,
)
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    substitute_placeholder_defaults,
    table_function_analysis_name,
)
from sqlbuild.compiler.compile._helpers.analysis.compact import (
    NativeCompactAnalysis,
    analyze_columns_and_lineage_with_polyglot,
    analyze_queries_with_compact_polyglot_batch,
    get_complete_schema_binding_request,
    infer_columns_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.analysis.dynamic_pivot import (
    analyze_dynamic_column_contract,
)
from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_hook_sql_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile._helpers.assembly.binding_positions import (
    get_authored_binding_location,
    query_line_offset,
)
from sqlbuild.compiler.compile._helpers.assembly.binding_waves import analyze_binding_waves
from sqlbuild.compiler.compile._helpers.assembly.binding_waves import (
    downstream_model_names as _downstream_model_names,
)
from sqlbuild.compiler.compile._helpers.assembly.binding_waves import (
    referenced_model_names as _referenced_model_names,
)
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    binding_required_names,
    binding_schema_for_model,
    build_complete_binding_schemas,
    get_expression_source_shape,
    inferred_binding_shape,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    build_declared_column_types as _build_column_types_by_table,
)
from sqlbuild.compiler.compile._helpers.assembly.targets import (
    build_model_relation_target,
    build_seed_relation_target,
)
from sqlbuild.compiler.compile._helpers.config.namespace_validation import (
    validate_preserved_logical_namespace,
)
from sqlbuild.compiler.compile._helpers.deps.dependencies import (
    audit_scope_deps,
    function_build_deps,
    model_build_deps,
    sql_test_scope_deps,
)
from sqlbuild.compiler.compile._helpers.diagnostics.recovery import complete_semantic_diagnostics
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    resolve_early_model_templates,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_declaration_scope_resolver,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    find_macro_call_names,
)
from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile._helpers.sql_tests.core import extract_assertion_target_model_names
from sqlbuild.compiler.compile._helpers.sql_tests.identity import (
    build_sql_test_case_fingerprint,
)
from sqlbuild.compiler.compile.constants import NOT_NULL_AUDIT_NAME
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._scope_index_with_compile_usages import (
    scope_index_with_compile_usages,
)
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompactAnalysisCacheCandidate,
    CompactAnalysisCacheModel,
    CompactAnalysisCachePlan,
    CompactBatchExecutionOptions,
    CompactBatchPreparation,
    CompileAuditInput,
    CompiledAudit,
    CompiledDirectLogicSqlTestPayload,
    CompiledFunction,
    CompileDirectLogicSqlTestInputPayload,
    CompiledLineageColumnFact,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompiledSqlScenario,
    CompiledSqlTest,
    CompiledSqlTestResource,
    CompileModelInput,
    CompileModelSqlTestInputPayload,
    CompileProjectInputs,
    CompilerDiagnostic,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
    DynamicColumnContractProof,
    InferredColumn,
    MacroContext,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysis as _ModelSqlAnalysis,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysisRequest as _ModelSqlAnalysisRequest,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompactBatchResponseCallback,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    SqlTestMode,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.resource_names.main.function_node_type import function_node_type
from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.main._validate_scope_index import validate_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.sql_analysis.constants import (
    BINDING_UNKNOWN_TABLE_INTERNAL_CODE,
    NATIVE_DIALECT_ALIASES,
)
from sqlbuild.compiler.sql_analysis.exceptions import SqlAnalysisBoundaryError
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._identifier_case import ignores_quoted_case
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    SchemaAuditInstance,
    SchemaColumn,
    SchemaDynamicColumnFamily,
    SourceColumnEntry,
    SourceEntry,
    SourceLocation,
    TargetConfig,
)


@dataclass(frozen=True)
class _DynamicContractAnalysisInputs:
    families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]]
    authoritative_column_types_by_table: dict[str, dict[str, str]]


_COMPACT_BATCH_CACHE_MIN_MODEL_COUNT: int = 256
_COMPACT_BATCH_ENTRY_REUSE_MIN_PERCENT: int = 10


def assemble_compiled_project(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProject:
    """Convert attached compile inputs into the planner-ready project view."""

    sql_analysis_enabled: bool = (
        inputs.effective_settings.sql_analysis and not skip_column_inference
    )
    seed_names: frozenset[str] = frozenset(
        seed_input.schema_entry.name for seed_input in inputs.seed_inputs
    )
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] = (
        _build_column_nullability_by_table(inputs)
    )
    column_types_by_table: dict[str, dict[str, str]] = _build_column_types_by_table(inputs)
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]] = (
        _build_dynamic_families_by_table(inputs)
    )
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    profile = replace(
        profile,
        semantic_known_functions=known_function_names(inputs.sql_function_inputs),
        semantic_known_types=known_declared_types(
            functions=inputs.sql_function_inputs, column_types=column_types_by_table
        ),
        quoted_identifiers_ignore_case=ignores_quoted_case(
            connection=inputs.effective_connection, dialect=profile.sql_analysis_dialect
        ),
        sql_analysis_dialect=NATIVE_DIALECT_ALIASES.get(
            profile.sql_analysis_dialect or "", profile.sql_analysis_dialect
        ),
        function_return_types={
            **profile.function_return_types,
            **{
                f"__sqlbuild_udf_{function.name}".upper(): function.returns
                for function in inputs.sql_function_inputs
                if not function.return_columns
            },
        },
    )
    complete_binding_schemas: dict[str, dict[str, str]] = build_complete_binding_schemas(inputs)
    binding_catalog: Any = create_binding_catalog(
        dialect=profile.sql_analysis_dialect or "generic",
        quoted_ignore_case=profile.quoted_identifiers_ignore_case,
        known_functions=profile.semantic_known_functions,
        known_types=profile.semantic_known_types,
        relations={},
    )
    profile = replace(profile, binding_catalog=binding_catalog)
    if sql_analysis_enabled:
        for source_input in inputs.source_inputs:
            expression: str | None = source_input.source_entry.expression
            if expression:
                shape: dict[str, str] | None = get_expression_source_shape(
                    expression=expression, profile=profile
                )
                if shape is not None:
                    declared_types: dict[str, str] = column_types_by_table.get(
                        source_input.source_entry.name, {}
                    )
                    shape = {
                        name: declared_types.get(name, column_type)
                        for name, column_type in shape.items()
                    }
                    complete_binding_schemas[source_input.source_entry.name] = shape
                    column_types_by_table[source_input.source_entry.name] = shape
                    column_nullability_by_table[source_input.source_entry.name] = {
                        name: column_nullability_by_table.get(
                            source_input.source_entry.name, {}
                        ).get(name, InferredNullability.UNKNOWN)
                        for name in shape
                    }
    binding_catalog.native.update_relations(complete_binding_schemas)
    binding_catalog.schemas.update(complete_binding_schemas)
    dynamic_contract_analysis_inputs: _DynamicContractAnalysisInputs = (
        _DynamicContractAnalysisInputs(
            families_by_table=dynamic_families_by_table,
            authoritative_column_types_by_table=complete_binding_schemas,
        )
    )
    allow_compact_analysis: bool = column_lineage_mode in {
        ColumnLineageMode.FAST,
        ColumnLineageMode.RICH,
    }
    rich_type_inference: bool = column_lineage_mode == ColumnLineageMode.RICH
    analysis_cache: AnalysisCacheContext | None = (
        build_analysis_cache_context(
            root=analysis_cache_dir,
            inference_profile=profile,
            allow_compact_analysis=allow_compact_analysis,
            rich_type_inference=rich_type_inference,
            signature_namespace={
                "known_functions": known_function_names(inputs.sql_function_inputs),
                "known_types": known_declared_types(
                    functions=inputs.sql_function_inputs, column_types=column_types_by_table
                ),
                "target": inputs.effective_target_name,
                "vars": inputs.effective_vars,
            },
        )
        if sql_analysis_enabled and analysis_model_names != frozenset()
        else None
    )
    model_sql_analysis_by_name: dict[str, _ModelSqlAnalysis] = {}
    if sql_analysis_enabled:
        with record_compile_timing("model_analysis_ms"):
            model_sql_analysis_by_name = _analyze_model_sql_in_parallel(
                known_functions=known_function_names(inputs.sql_function_inputs),
                known_types=known_declared_types(
                    functions=inputs.sql_function_inputs, column_types=column_types_by_table
                ),
                model_inputs=tuple(
                    model_input
                    for model_input in inputs.model_inputs
                    if model_input.sql_validation_enabled
                    and (
                        analysis_model_names is None
                        or _model_name(model_input) in analysis_model_names
                    )
                ),
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                inference_profile=profile,
                allow_compact_analysis=allow_compact_analysis,
                rich_type_inference=rich_type_inference,
                analysis_cache=analysis_cache,
                complete_binding_schemas=complete_binding_schemas,
            )
    scope_index: ScopeIndex = scope_index_with_compile_usages(inputs=inputs)
    try:
        validate_scope_index(index=scope_index)
    except ScopeValidationError as error:
        raise CompileInputError(str(error)) from error
    effective_target_values: dict[str, object] = resolve_early_model_templates(
        values={
            "database": (
                (inputs.effective_target.database if inputs.effective_target is not None else None)
                or _connection_database_fallback(inputs=inputs)
            ),
            "schema": (
                (inputs.effective_target.schema if inputs.effective_target is not None else None)
                or _str_or_none(inputs.effective_connection.get("schema"))
            ),
        },
        effective_vars=inputs.effective_vars,
        effective_target_name=inputs.effective_target_name,
        run_id=inputs.run_id,
    )
    project: CompiledProject = CompiledProject(
        binding_catalog=profile.binding_catalog,
        sql_expansions={
            model_input.model_file.file_path: model_input.sql_expansion
            for model_input in inputs.model_inputs
            if model_input.sql_expansion is not None
        },
        run_id=inputs.run_id,
        effective_target_name=inputs.effective_target_name,
        effective_connection=inputs.effective_connection,
        effective_vars=inputs.effective_vars,
        effective_target_database=_str_or_none(effective_target_values.get("database")),
        effective_target_schema=_str_or_none(effective_target_values.get("schema")),
        sql_analysis_dialect=profile.sql_analysis_dialect,
        compile_cache_dir=inputs.compile_cache_dir,
        settings=inputs.effective_settings,
        scenario=resolve_effective_scenario_config(
            project_config=inputs.project_config,
            local_config=inputs.local_config,
        ),
        models=tuple(
            _assemble_compiled_model(
                model_input=model_input,
                sql_analysis_enabled=(
                    sql_analysis_enabled
                    and model_input.sql_validation_enabled
                    and (
                        analysis_model_names is None
                        or _model_name(model_input) in analysis_model_names
                    )
                ),
                sql_validation_enabled=(
                    analysis_model_names is None or _model_name(model_input) in analysis_model_names
                ),
                seed_names=seed_names,
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                dynamic_contract_analysis_inputs=dynamic_contract_analysis_inputs,
                inference_profile=profile,
                sql_analysis=model_sql_analysis_by_name.get(model_input.model_file.file_path.stem),
                allow_compact_analysis=allow_compact_analysis,
            )
            for model_input in inputs.model_inputs
        ),
        sources=tuple(
            _assemble_compiled_source(
                source_input=source_input,
                target_config=inputs.effective_target,
                effective_vars=inputs.effective_vars,
            )
            for source_input in inputs.source_inputs
        ),
        seeds=tuple(
            _assemble_compiled_seed(
                seed_input=seed_input,
                defaults=inputs.project_config.defaults,
                target_config=inputs.effective_target,
                effective_vars=inputs.effective_vars,
            )
            for seed_input in inputs.seed_inputs
        ),
        functions=tuple(
            _assemble_compiled_function(function_input=function_input, seed_names=seed_names)
            for function_input in inputs.sql_function_inputs
        ),
        audits=tuple(_assemble_compiled_audit(audit_input) for audit_input in inputs.audit_inputs),
        sql_tests=tuple(
            _assemble_compiled_sql_test(
                test_input=test_input, model_inputs=inputs.model_inputs, inputs=inputs
            )
            for test_input in inputs.test_inputs
        ),
        sql_scenarios=tuple(
            _assemble_compiled_sql_scenario(scenario_input)
            for scenario_input in inputs.scenario_inputs
        ),
        loader_functions=inputs.discovered_inputs.loader_functions,
        hook_functions=inputs.discovered_inputs.hook_functions,
        sql_hook_files=inputs.discovered_inputs.sql_hook_files,
        materialization_files=inputs.discovered_inputs.materialization_files,
        public_enums=inputs.public_enums,
        public_constants=inputs.public_constants,
        loaded_macros=inputs.loaded_macros,
        diagnostics=(
            *inputs.diagnostics,
            *_project_binding_diagnostics(
                model_inputs=inputs.model_inputs,
                analyses_by_name=model_sql_analysis_by_name,
                dialect=profile.sql_analysis_dialect,
            ),
        ),
        external_sql_reference_resolver=inputs.external_sql_reference_resolver,
        scope_index=scope_index,
    )
    return complete_semantic_diagnostics(
        project=project,
        profile=profile,
        binding_results={
            name: analysis.polyglot_analysis.binding_diagnostics
            for name, analysis in model_sql_analysis_by_name.items()
        },
    )


def _str_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _connection_database_fallback(*, inputs: CompileProjectInputs) -> str | None:
    adapter_name: str = resolve_effective_adapter_name(
        project_config=inputs.project_config,
        local_config=inputs.local_config,
    )
    if adapter_name == BuiltinAdapter.DUCKDB:
        return None
    return _str_or_none(inputs.effective_connection.get("database"))


def _assemble_compiled_model(
    *,
    model_input: CompileModelInput,
    sql_analysis_enabled: bool,
    sql_validation_enabled: bool = True,
    seed_names: frozenset[str] = frozenset(),
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    column_types_by_table: dict[str, dict[str, str]] | None = None,
    dynamic_contract_analysis_inputs: _DynamicContractAnalysisInputs | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
    sql_analysis: _ModelSqlAnalysis | None = None,
    allow_compact_analysis: bool = False,
) -> CompiledModel:
    model_name: str = model_input.model_file.file_path.stem
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    analysis_query_sql: str = cursor_intrinsics_analysis_sql(
        sql=model_input.query_sql,
        cursor_type=model_input.config.values.get("cursor_type"),
    )
    inferred_columns: tuple[InferredColumn, ...] | None = None
    fast_lineage_columns: Sequence[CompiledLineageColumnFact] | None = None
    fast_lineage_has_star: bool = False
    fast_lineage_star_resolved: bool = False
    placeholders: dict[str, str] | None = (
        sql_analysis.placeholders if sql_analysis is not None else _model_placeholders(model_input)
    )
    if sql_validation_enabled and model_input.sql_validation_enabled:
        for hook_name in ("pre_hooks", "post_hooks"):
            validate_hook_sql_syntax(
                value=model_input.config.values.get(hook_name),
                hook_name=hook_name,
                model_name=model_name,
                file_path=model_input.model_file.file_path,
                placeholders=placeholders,
                dialect=profile.sql_analysis_dialect,
            )
    if sql_analysis_enabled:
        polyglot_analysis: PolyglotAnalysisResult = (
            sql_analysis.polyglot_analysis
            if sql_analysis is not None
            else analyze_columns_and_lineage_with_polyglot(
                query_sql=analysis_query_sql,
                references=model_input.references,
                placeholders=placeholders,
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                inference_profile=profile,
                allow_compact_analysis=allow_compact_analysis,
            )
        )
        if polyglot_analysis.analysis_succeeded:
            inferred_columns = polyglot_analysis.columns
            fast_lineage_columns = polyglot_analysis.lineage_columns
            fast_lineage_has_star = polyglot_analysis.has_star
            fast_lineage_star_resolved = polyglot_analysis.star_resolved
        else:
            if model_input.sql_validation_enabled:
                validate_sql_syntax(
                    query_sql=analysis_query_sql,
                    model_name=model_name,
                    file_path=model_input.model_file.file_path,
                    placeholders=placeholders,
                    dialect=profile.sql_analysis_dialect,
                )
            inferred_columns = infer_columns_with_sql_analysis(
                query_sql=analysis_query_sql,
                placeholders=placeholders,
                column_nullability_by_table=column_nullability_by_table,
                inference_profile=profile,
            )
    elif sql_validation_enabled and model_input.sql_validation_enabled:
        validate_sql_syntax(
            query_sql=analysis_query_sql,
            model_name=model_name,
            file_path=model_input.model_file.file_path,
            placeholders=placeholders,
            dialect=profile.sql_analysis_dialect,
        )
    dynamic_column_contract: DynamicColumnContractProof | None = analyze_dynamic_column_contract(
        query_sql=(
            substitute_placeholder_defaults(
                query_sql=analysis_query_sql,
                placeholders=placeholders,
            )
            if placeholders
            else analysis_query_sql
        ),
        dialect=profile.sql_analysis_dialect,
        families=(
            model_input.schema_entry.dynamic_columns if model_input.schema_entry is not None else ()
        ),
        column_types_by_table=column_types_by_table or {},
        authoritative_column_types_by_table=(
            dynamic_contract_analysis_inputs.authoritative_column_types_by_table
            if dynamic_contract_analysis_inputs is not None
            else {}
        ),
        column_nullability_by_table=column_nullability_by_table or {},
        dynamic_families_by_table=(
            dynamic_contract_analysis_inputs.families_by_table
            if dynamic_contract_analysis_inputs is not None
            else {}
        ),
    )
    if dynamic_column_contract is not None and dynamic_column_contract.output_proven:
        inferred_columns = dynamic_column_contract.fixed_columns
        fast_lineage_has_star = True
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
        deps=model_build_deps(references=model_input.references, seed_names=seed_names),
        name=model_name,
        relative_path=model_input.model_file.relative_path,
        query_sql=model_input.query_sql,
        config=model_input.config,
        destination=build_model_relation_target(model_input=model_input, model_name=model_name),
        references=model_input.references,
        schema_entry=model_input.schema_entry,
        inferred_columns=inferred_columns,
        fast_lineage_columns=fast_lineage_columns,
        fast_lineage_has_star=fast_lineage_has_star,
        fast_lineage_star_resolved=fast_lineage_star_resolved,
        authored_sql=model_input.model_file.contents,
        authored_query_sql=model_input.model_file.query_sql,
        output_column_locations=model_input.model_file.output_column_locations,
        extract_implicit_alias_columns=model_input.model_file.extract_implicit_alias_columns,
        macro_deps=model_input.macro_deps or find_macro_call_names(model_input.macro_source_sql),
        enum_declarations=model_input.enum_declarations,
        constant_declarations=model_input.constant_declarations,
        enum_columns=model_input.enum_columns,
        binding_diagnostics=_binding_compiler_diagnostics(
            model_input=model_input,
            cleaned_sql=sql_analysis.cleaned_sql if sql_analysis is not None else None,
            dialect=profile.sql_analysis_dialect,
            diagnostics=(polyglot_analysis.binding_diagnostics if sql_analysis_enabled else ()),
        ),
        binding_validated=(polyglot_analysis.binding_validated if sql_analysis_enabled else False),
        dynamic_column_contract=dynamic_column_contract,
    )


def _analyze_model_sql_in_parallel(
    *,
    known_functions: tuple[str, ...],
    known_types: tuple[str, ...],
    model_inputs: tuple[CompileModelInput, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    rich_type_inference: bool,
    analysis_cache: AnalysisCacheContext | None,
    complete_binding_schemas: dict[str, dict[str, str]],
) -> dict[str, _ModelSqlAnalysis]:
    if not model_inputs:
        return {}
    analyzed_model_names: frozenset[str] = frozenset(
        _model_name(model_input) for model_input in model_inputs
    )
    requests: tuple[_ModelSqlAnalysisRequest, ...] = tuple(
        _model_sql_analysis_request(
            model_input=model_input,
            analysis_cache=analysis_cache,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            complete_binding_schemas=complete_binding_schemas,
        )
        for model_input in model_inputs
    )
    request_cache_keys: tuple[str, ...] = tuple(
        request.cache_key for request in requests if request.cache_key is not None
    )
    dependency_ordered: bool = allow_compact_analysis and any(
        request.binding_schema is not None and not all(request.binding_schema.values())
        for request in requests
    )
    compact_batch_plan: CompactAnalysisCachePlan | None = None
    if analysis_cache is not None:
        compact_batch_plan = build_compact_analysis_cache_plan(
            context=analysis_cache,
            models=tuple(
                CompactAnalysisCacheModel(
                    name=_model_name(request.model_input),
                    cache_key=request.cache_key,
                    upstream_names=_referenced_model_names(
                        model_input=request.model_input,
                        available_names=analyzed_model_names,
                    ),
                )
                for request in requests
            ),
            min_model_count=_COMPACT_BATCH_CACHE_MIN_MODEL_COUNT,
        )
    compact_cached_analyses: dict[str, PolyglotAnalysisResult] = {}
    compact_batch_hit_count: int = 0
    compact_candidate: CompactAnalysisCacheCandidate | None = (
        read_compact_analysis_cache_candidate(
            plan=compact_batch_plan,
            expected_count=len(requests),
            min_model_count=_COMPACT_BATCH_CACHE_MIN_MODEL_COUNT,
        )
        if compact_batch_plan is not None and not dependency_ordered
        else None
    )
    if compact_candidate is not None:
        completed_analyses: dict[str, PolyglotAnalysisResult] = {}
        if analysis_cache is not None:
            completed_analyses, _, _ = read_model_analyses(
                context=analysis_cache,
                cache_keys=request_cache_keys,
                model_names=tuple(_model_name(request.model_input) for request in requests),
                upstream_model_names_by_key={
                    request.cache_key: _referenced_model_names(
                        model_input=request.model_input,
                        available_names=analyzed_model_names,
                    )
                    for request in requests
                    if request.cache_key is not None
                },
            )
            if all(key in completed_analyses for key in request_cache_keys):
                record_analysis_cache_metrics(
                    batch_hits=len(requests), entry_hits=0, misses=0, bypasses=0
                )
                return {
                    _model_name(request.model_input): _ModelSqlAnalysis(
                        polyglot_analysis=completed_analyses[cache_key],
                        placeholders=request.placeholders,
                    )
                    for request, cache_key in zip(requests, request_cache_keys, strict=True)
                }
        try:
            compact_analyses: tuple[_ModelSqlAnalysis, ...] = _analyze_model_sql_requests(
                requests=requests,
                cached_analyses=completed_analyses,
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                inference_profile=inference_profile,
                allow_compact_analysis=allow_compact_analysis,
                rich_type_inference=rich_type_inference,
                cached_compact_batch=(
                    compact_candidate.preparation,
                    compact_candidate.response,
                ),
            )
        except SqlAnalysisBoundaryError:
            pass
        else:
            compact_cached_analyses = {
                request_cache_keys[index]: compact_analyses[index].polyglot_analysis
                for index in compact_candidate.matching_indexes
            }
            compact_batch_hit_count = len(compact_candidate.matching_indexes)
            if compact_batch_hit_count == len(requests):
                record_analysis_cache_metrics(
                    batch_hits=compact_batch_hit_count,
                    entry_hits=0,
                    misses=0,
                    bypasses=0,
                )
                compact_analyses = _complete_inferred_bindings(
                    known_functions=known_functions,
                    known_types=known_types,
                    requests=requests,
                    analyses=compact_analyses,
                    complete_binding_schemas=complete_binding_schemas,
                    inference_profile=inference_profile,
                )
                return {
                    _model_name(model_input): analysis
                    for model_input, analysis in zip(model_inputs, compact_analyses, strict=True)
                }
    entry_cache_keys: tuple[str, ...] = tuple(
        cache_key for cache_key in request_cache_keys if cache_key not in compact_cached_analyses
    )
    cached_analyses: dict[str, PolyglotAnalysisResult]
    previous_signatures: dict[str, str]
    cached_output_signatures_by_key: dict[str, str]
    cached_analyses, previous_signatures, cached_output_signatures_by_key = (
        read_model_analyses(
            context=analysis_cache,
            cache_keys=entry_cache_keys,
            model_names=tuple(_model_name(request.model_input) for request in requests),
            upstream_model_names_by_key={
                request.cache_key: _referenced_model_names(
                    model_input=request.model_input,
                    available_names=analyzed_model_names,
                )
                for request in requests
                if request.cache_key is not None
                and request.cache_key not in compact_cached_analyses
            },
        )
        if analysis_cache is not None
        else ({}, {}, {})
    )
    entry_cache_hit_count: int = sum(
        request.cache_key is not None and request.cache_key in cached_analyses
        for request in requests
    )
    if (
        compact_batch_plan is not None
        and compact_batch_hit_count == 0
        and entry_cache_hit_count > 0
        and entry_cache_hit_count * 100 < len(requests) * _COMPACT_BATCH_ENTRY_REUSE_MIN_PERCENT
    ):
        cached_analyses.clear()
        cached_output_signatures_by_key.clear()
        entry_cache_hit_count = 0
    cached_analyses.update(compact_cached_analyses)
    cached_output_signatures_by_key.update(
        {
            cache_key: model_analysis_output_signature(analysis)
            for cache_key, analysis in compact_cached_analyses.items()
        }
    )
    analyses: tuple[_ModelSqlAnalysis, ...]
    if dependency_ordered:
        analyses, cached_analyses = analyze_binding_waves(
            requests=requests,
            names=tuple(_model_name(request.model_input) for request in requests),
            cached=cached_analyses,
            previous_signatures=previous_signatures,
            shapes=complete_binding_schemas,
            types=column_types_by_table,
            nullability=column_nullability_by_table,
            profile=inference_profile,
            analyze=partial(
                _analyze_model_sql_requests,
                inference_profile=inference_profile,
                allow_compact_analysis=allow_compact_analysis,
                rich_type_inference=rich_type_inference,
            ),
            complete=partial(
                _complete_inferred_bindings,
                known_functions=known_functions,
                known_types=known_types,
                inference_profile=inference_profile,
            ),
        )
        if compact_batch_plan is not None:
            compact_batch_hit_count = sum(analysis.cached for analysis in analyses)
            entry_cache_hit_count -= compact_batch_hit_count
    else:
        analyses = _analyze_model_sql_requests(
            requests=requests,
            cached_analyses=cached_analyses,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            inference_profile=inference_profile,
            allow_compact_analysis=allow_compact_analysis,
            rich_type_inference=rich_type_inference,
            on_compact_response=(
                compact_analysis_batch_response_writer(
                    plan=compact_batch_plan,
                    count=len(requests),
                )
                if compact_batch_plan is not None and not cached_analyses
                else None
            ),
        )
        analyses = _complete_inferred_bindings(
            known_functions=known_functions,
            known_types=known_types,
            requests=requests,
            analyses=analyses,
            complete_binding_schemas=complete_binding_schemas,
            inference_profile=inference_profile,
        )
    record_analysis_cache_metrics(
        batch_hits=compact_batch_hit_count,
        entry_hits=entry_cache_hit_count,
        misses=(
            len(requests) - compact_batch_hit_count - entry_cache_hit_count
            if analysis_cache is not None
            else 0
        ),
        bypasses=(len(requests) if analysis_cache is None else 0),
    )
    if analysis_cache is None:
        return {
            _model_name(model_input): analysis
            for model_input, analysis in zip(model_inputs, analyses, strict=True)
        }
    current_analyses_by_name: dict[str, PolyglotAnalysisResult] = {
        _model_name(request.model_input): analysis.polyglot_analysis
        for request, analysis in zip(requests, analyses, strict=True)
    }
    current_signatures_by_name: dict[str, str] = {
        _model_name(request.model_input): (
            cached_output_signatures_by_key[request.cache_key]
            if request.cache_key is not None and request.cache_key in cached_analyses
            else model_analysis_output_signature(analysis.polyglot_analysis)
        )
        for request, analysis in zip(requests, analyses, strict=True)
    }
    analyses_to_record_by_name: dict[str, PolyglotAnalysisResult] = {
        _model_name(request.model_input): analysis.polyglot_analysis
        for request, analysis in zip(requests, analyses, strict=True)
        if request.cache_key is None or request.cache_key not in cached_analyses
    }
    changed_signature_names: set[str] = {
        _model_name(request.model_input)
        for request, analysis in zip(requests, analyses, strict=True)
        if (
            previous_signatures.get(_model_name(request.model_input))
            != current_signatures_by_name[_model_name(request.model_input)]
            or (
                not analysis.polyglot_analysis.analysis_succeeded
                and request.cache_key not in cached_analyses
            )
        )
    }
    analyses_to_record_by_name.update(
        {model_name: current_analyses_by_name[model_name] for model_name in changed_signature_names}
    )
    invalidated_names: set[str] = _downstream_model_names(
        model_inputs=model_inputs,
        changed_names=changed_signature_names,
    )
    if invalidated_names and not dependency_ordered:
        invalidated_requests: tuple[_ModelSqlAnalysisRequest, ...] = tuple(
            request
            for request in requests
            if (
                _model_name(request.model_input) in invalidated_names
                and request.cache_key is not None
                and request.cache_key in cached_analyses
            )
        )
        invalidated_analyses_by_name: dict[str, _ModelSqlAnalysis] = {
            _model_name(request.model_input): analysis
            for request, analysis in zip(
                invalidated_requests,
                _analyze_model_sql_requests(
                    requests=invalidated_requests,
                    cached_analyses={},
                    column_nullability_by_table=column_nullability_by_table,
                    column_types_by_table=column_types_by_table,
                    inference_profile=inference_profile,
                    allow_compact_analysis=allow_compact_analysis,
                    rich_type_inference=rich_type_inference,
                ),
                strict=True,
            )
        }
        analyses = tuple(
            invalidated_analyses_by_name.get(_model_name(request.model_input), analysis)
            for request, analysis in zip(requests, analyses, strict=True)
        )
        analyses = _complete_inferred_bindings(
            known_functions=known_functions,
            known_types=known_types,
            requests=requests,
            analyses=analyses,
            complete_binding_schemas=complete_binding_schemas,
            inference_profile=inference_profile,
        )
        invalidated_analyses_by_name = {
            _model_name(request.model_input): analysis
            for request, analysis in zip(requests, analyses, strict=True)
            if _model_name(request.model_input) in invalidated_names
        }
        analyses_to_record_by_name.update(
            {
                _model_name(request.model_input): analysis.polyglot_analysis
                for request, analysis in zip(requests, analyses, strict=True)
                if _model_name(request.model_input) in invalidated_names
            }
        )
        current_analyses_by_name = {
            _model_name(request.model_input): analysis.polyglot_analysis
            for request, analysis in zip(requests, analyses, strict=True)
        }
        current_signatures_by_name.update(
            {
                model_name: model_analysis_output_signature(invalidated_analysis.polyglot_analysis)
                for model_name, invalidated_analysis in invalidated_analyses_by_name.items()
            }
        )
    if analysis_cache is not None:
        with record_compile_timing("cache_publication_ms"):
            write_model_analyses(
                context=analysis_cache,
                analyses_by_key={
                    request.cache_key: analysis.polyglot_analysis
                    for request, analysis in zip(requests, analyses, strict=True)
                    if request.cache_key is not None
                    and (
                        request.cache_key not in cached_analyses
                        or _model_name(request.model_input) in invalidated_names
                    )
                },
                latest_analyses_by_model=analyses_to_record_by_name,
                dependency_signatures_by_key=_dependency_signatures_by_key(
                    requests=requests,
                    cached_analyses=cached_analyses,
                    invalidated_names=invalidated_names,
                    current_signatures_by_name=current_signatures_by_name,
                    analyzed_model_names=analyzed_model_names,
                ),
            )
    return {
        _model_name(model_input): analysis
        for model_input, analysis in zip(model_inputs, analyses, strict=True)
    }


def _analyze_model_sql_requests(
    *,
    requests: tuple[_ModelSqlAnalysisRequest, ...],
    cached_analyses: dict[str, PolyglotAnalysisResult],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    rich_type_inference: bool,
    cached_compact_batch: tuple[CompactBatchPreparation, object] | None = None,
    on_compact_response: CompactBatchResponseCallback | None = None,
) -> tuple[_ModelSqlAnalysis, ...]:
    if allow_compact_analysis:
        uncached: tuple[tuple[int, _ModelSqlAnalysisRequest], ...] = tuple(
            (index, request)
            for index, request in enumerate(requests)
            if request.cache_key is None or request.cache_key not in cached_analyses
        )
        prepared_by_index: dict[int, NativeCompactAnalysis] = {}
        diagnostics_by_index: dict[int, tuple[SqlBindingDiagnostic, ...]] = {}
        if uncached:
            batch_requests: tuple[tuple[int, _ModelSqlAnalysisRequest], ...] = (
                tuple(enumerate(requests)) if cached_compact_batch is not None else uncached
            )
            prepared: tuple[NativeCompactAnalysis, ...] = (
                analyze_queries_with_compact_polyglot_batch(
                    query_sqls=tuple(request.query_sql for _, request in batch_requests),
                    references=tuple(
                        request.model_input.references for _, request in batch_requests
                    ),
                    placeholders=tuple(request.placeholders for _, request in batch_requests),
                    column_nullability_by_table=column_nullability_by_table,
                    column_types_by_table=column_types_by_table,
                    inference_profile=inference_profile,
                    recover_cte_facts=tuple(
                        _should_recover_cte_facts(request.model_input)
                        for _, request in batch_requests
                    ),
                    rich_type_inference=rich_type_inference,
                    cached_batch=cached_compact_batch,
                    execution=CompactBatchExecutionOptions(
                        on_response=(
                            on_compact_response if len(uncached) == len(requests) else None
                        ),
                        binding_schemas=tuple(
                            request.binding_schema for _, request in batch_requests
                        ),
                    ),
                )
            )
            prepared_by_index = {
                index: value for (index, _), value in zip(batch_requests, prepared, strict=True)
            }
            validation_indices: tuple[int, ...] = tuple(
                index
                for index, request in uncached
                if request.binding_schema is not None
                and prepared_by_index[index].binding_diagnostics is None
            )
            with record_compile_timing("binding_validation_ms"):
                validation_results: tuple[SqlBindingResult, ...] = get_schema_validations(
                    requests=tuple(
                        SqlSchemaValidationRequest(
                            sql=prepared_by_index[index].cleaned_sql,
                            dialect=inference_profile.sql_analysis_dialect,
                            schema=requests[index].binding_schema or {},
                            known_functions=inference_profile.semantic_known_functions,
                            known_types=inference_profile.semantic_known_types,
                            quoted_identifiers_ignore_case=inference_profile.quoted_identifiers_ignore_case,
                            catalog=inference_profile.binding_catalog,
                        )
                        for index in validation_indices
                    )
                )
            diagnostics_by_index = {
                index: result.diagnostics
                for index, result in zip(validation_indices, validation_results, strict=True)
            }
        return tuple(
            _analyze_model_sql(
                request=request,
                cached_analysis=(
                    cached_analyses.get(request.cache_key)
                    if request.cache_key is not None
                    else None
                ),
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                inference_profile=inference_profile,
                allow_compact_analysis=True,
                precomputed=(
                    replace(
                        prepared_by_index[index],
                        binding_diagnostics=diagnostics_by_index.get(
                            index, prepared_by_index[index].binding_diagnostics
                        ),
                    )
                    if index in prepared_by_index
                    else None
                ),
            )
            for index, request in enumerate(requests)
        )

    def analyze(request: _ModelSqlAnalysisRequest) -> _ModelSqlAnalysis:
        return _analyze_model_sql(
            request=request,
            cached_analysis=(
                cached_analyses.get(request.cache_key) if request.cache_key is not None else None
            ),
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            inference_profile=inference_profile,
            allow_compact_analysis=allow_compact_analysis,
        )

    return tuple(analyze(request) for request in requests)


def _complete_inferred_bindings(
    *,
    known_functions: tuple[str, ...],
    known_types: tuple[str, ...],
    requests: tuple[_ModelSqlAnalysisRequest, ...],
    analyses: tuple[_ModelSqlAnalysis, ...],
    complete_binding_schemas: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[_ModelSqlAnalysis, ...]:
    """Bind each scope independently, preserving open inputs as empty tables."""

    complete_schemas: dict[str, dict[str, str]] = dict(complete_binding_schemas)
    results: list[_ModelSqlAnalysis] = list(analyses)
    indexes: dict[str, int] = {
        _model_name(request.model_input): index for index, request in enumerate(requests)
    }
    available_names: frozenset[str] = frozenset(indexes)
    graph: dict[str, tuple[str, ...]] = {
        name: _referenced_model_names(
            model_input=requests[index].model_input, available_names=available_names
        )
        for name, index in indexes.items()
    }
    try:
        ordered_names: tuple[str, ...] = tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        return analyses
    for name in ordered_names:
        index: int = indexes[name]
        request: _ModelSqlAnalysisRequest = requests[index]
        required_names: frozenset[str] | None = binding_required_names(request.model_input)
        if required_names is None:
            continue
        analysis: PolyglotAnalysisResult = results[index].polyglot_analysis
        if (
            not results[index].cached
            and required_names
            and (
                any(column.type is None for column in analysis.columns or ())
                or (
                    analysis.has_star
                    and not analysis.columns
                    and required_names <= complete_schemas.keys()
                )
            )
            and not re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", request.query_sql, re.IGNORECASE)
        ):
            input_schemas: dict[str, dict[str, str]] = {
                table: complete_schemas[table]
                for table in required_names
                if table in complete_schemas
            }
            nullability: dict[str, dict[str, InferredNullability]] = {
                table: dict.fromkeys(columns, InferredNullability.UNKNOWN)
                for table, columns in input_schemas.items()
            }
            enriched: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
                query_sql=request.query_sql,
                references=request.model_input.references,
                placeholders=request.placeholders,
                column_types_by_table=input_schemas,
                column_nullability_by_table=nullability,
                inference_profile=inference_profile,
                allow_compact_analysis=True,
                recover_cte_facts=_should_recover_cte_facts(request.model_input),
            )
            enriched_types: dict[str, str | None] = {
                column.name: column.type for column in enriched.columns or ()
            }
            if not analysis.columns and enriched.analysis_succeeded:
                analysis = enriched
            analysis = replace(
                analysis,
                columns=tuple(
                    replace(column, type=column.type or enriched_types.get(column.name))
                    for column in analysis.columns or ()
                ),
            )
            results[index] = replace(results[index], polyglot_analysis=analysis)
        if analysis.columns and (
            not analysis.has_star or (required_names and required_names <= complete_schemas.keys())
        ):
            complete_schemas.setdefault(
                name,
                inferred_binding_shape(
                    sql=results[index].cleaned_sql or request.query_sql,
                    profile=inference_profile,
                    columns={column.name: column.type or "UNKNOWN" for column in analysis.columns},
                    inputs={table: complete_schemas.get(table, {}) for table in required_names},
                ),
            )
    deferred_validation_indices: list[int] = []
    deferred_validation_requests: list[SqlSchemaValidationRequest] = []
    for index, request in enumerate(requests):
        if results[index].cached:
            continue
        required_names = binding_required_names(request.model_input)
        if required_names is None:
            continue
        if results[index].fused_binding_validated and (
            results[index].validated_schema or request.binding_schema
        ) == {name: complete_schemas.get(name, {}) for name in required_names}:
            continue
        deferred_validation_indices.append(index)
        deferred_validation_requests.append(
            replace(
                get_complete_schema_binding_request(
                    query_sql=request.query_sql,
                    cleaned_sql=results[index].cleaned_sql,
                    known_functions=known_functions,
                    known_types=known_types,
                    placeholders=request.placeholders,
                    dialect=inference_profile.sql_analysis_dialect,
                    binding_schema={
                        name: complete_schemas.get(name, {}) for name in required_names
                    },
                ),
                quoted_identifiers_ignore_case=inference_profile.quoted_identifiers_ignore_case,
                catalog=inference_profile.binding_catalog,
            )
        )
    with record_compile_timing("binding_validation_ms"):
        validation_results: tuple[SqlBindingResult, ...] = get_schema_validations(
            requests=tuple(deferred_validation_requests)
        )
    for index, validation_result in zip(
        deferred_validation_indices, validation_results, strict=True
    ):
        current: _ModelSqlAnalysis = results[index]
        results[index] = replace(
            current,
            polyglot_analysis=replace(
                current.polyglot_analysis,
                binding_diagnostics=validation_result.diagnostics,
                binding_validated=True,
            ),
        )
    return tuple(results)


def _dependency_signatures_by_key(
    *,
    requests: tuple[_ModelSqlAnalysisRequest, ...],
    cached_analyses: dict[str, PolyglotAnalysisResult],
    invalidated_names: set[str],
    current_signatures_by_name: dict[str, str],
    analyzed_model_names: frozenset[str],
) -> dict[str, dict[str, str]]:
    dependencies_by_key: dict[str, dict[str, str]] = {}
    for request in requests:
        cache_key: str | None = request.cache_key
        if cache_key is None or (
            cache_key in cached_analyses
            and _model_name(request.model_input) not in invalidated_names
        ):
            continue
        dependencies_by_key[cache_key] = {
            upstream_name: current_signatures_by_name[upstream_name]
            for upstream_name in _referenced_model_names(
                model_input=request.model_input,
                available_names=analyzed_model_names,
            )
            if upstream_name in current_signatures_by_name
        }
    return dependencies_by_key


def _analyze_model_sql(
    *,
    request: _ModelSqlAnalysisRequest,
    cached_analysis: PolyglotAnalysisResult | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    precomputed: NativeCompactAnalysis | None = None,
) -> _ModelSqlAnalysis:
    if cached_analysis is not None:
        return _ModelSqlAnalysis(
            polyglot_analysis=cached_analysis,
            placeholders=request.placeholders,
            cached=True,
        )
    polyglot_analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=request.query_sql,
        references=request.model_input.references,
        placeholders=request.placeholders,
        column_nullability_by_table=column_nullability_by_table,
        column_types_by_table=column_types_by_table,
        inference_profile=inference_profile,
        allow_compact_analysis=allow_compact_analysis,
        binding_schema=request.binding_schema,
        recover_cte_facts=_should_recover_cte_facts(request.model_input),
        precomputed=precomputed,
    )
    return _ModelSqlAnalysis(
        polyglot_analysis=polyglot_analysis,
        cleaned_sql=precomputed.cleaned_sql if precomputed is not None else None,
        placeholders=request.placeholders,
        validated_schema=request.binding_schema,
        fused_binding_validated=precomputed is not None
        and precomputed.binding_diagnostics is not None,
    )


def _model_sql_analysis_request(
    *,
    model_input: CompileModelInput,
    analysis_cache: AnalysisCacheContext | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    complete_binding_schemas: dict[str, dict[str, str]],
) -> _ModelSqlAnalysisRequest:
    placeholders: dict[str, str] | None = _model_placeholders(model_input)
    query_sql: str = cursor_intrinsics_analysis_sql(
        sql=model_input.query_sql,
        cursor_type=model_input.config.values.get("cursor_type"),
    )
    binding_schema: dict[str, dict[str, str]] | None = binding_schema_for_model(
        model_input=model_input,
        complete_binding_schemas=complete_binding_schemas,
    )
    cache_key: str | None = (
        model_analysis_cache_key(
            context=analysis_cache,
            query_sql=query_sql,
            references=model_input.references,
            placeholders=placeholders,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            binding_schema=binding_schema,
            recover_cte_facts=_should_recover_cte_facts(model_input),
        )
        if analysis_cache is not None
        else None
    )
    return _ModelSqlAnalysisRequest(
        model_input=model_input,
        query_sql=query_sql,
        placeholders=placeholders,
        cache_key=cache_key,
        binding_schema=binding_schema,
    )


def _model_placeholders(model_input: CompileModelInput) -> dict[str, str] | None:
    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    return (
        {str(k): str(v) for k, v in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
    )


def _should_recover_cte_facts(model_input: CompileModelInput) -> bool:
    return model_input.config.values.get("contract") == ContractPolicy.ENFORCED or (
        model_input.schema_entry is not None and bool(model_input.schema_entry.type_enforcement)
    )


def _model_name(model_input: CompileModelInput) -> str:
    return model_input.model_file.file_path.stem


def _build_column_nullability_by_table(
    inputs: CompileProjectInputs,
) -> dict[str, dict[str, InferredNullability]]:
    facts: dict[str, dict[str, InferredNullability]] = {}
    for model_input in inputs.model_inputs:
        if model_input.schema_entry is None:
            continue
        facts[model_input.schema_entry.name] = _schema_column_nullability(
            model_input.schema_entry.columns
        )
    for seed_input in inputs.seed_inputs:
        facts[seed_input.schema_entry.name] = _schema_column_nullability(
            seed_input.schema_entry.columns
        )
    for source_input in inputs.source_inputs:
        facts[source_input.source_entry.name] = _source_column_nullability(
            source_input.source_entry.columns
        )
    for function_input in inputs.sql_function_inputs:
        if not function_input.return_columns:
            continue
        facts[table_function_analysis_name(function_input.name)] = {
            column.name: InferredNullability.UNKNOWN for column in function_input.return_columns
        }
    return facts


def _build_dynamic_families_by_table(
    inputs: CompileProjectInputs,
) -> dict[str, tuple[SchemaDynamicColumnFamily, ...]]:
    return {
        model_input.schema_entry.name: model_input.schema_entry.dynamic_columns
        for model_input in inputs.model_inputs
        if model_input.config.values.get("contract") == ContractPolicy.ENFORCED
        and model_input.schema_entry is not None
        and model_input.schema_entry.dynamic_columns
    }


def _project_binding_diagnostics(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    analyses_by_name: dict[str, _ModelSqlAnalysis],
    dialect: str | None,
) -> tuple[CompilerDiagnostic, ...]:
    diagnostics: list[CompilerDiagnostic] = []
    for model_input in model_inputs:
        analysis: _ModelSqlAnalysis | None = analyses_by_name.get(_model_name(model_input))
        if analysis is None:
            continue
        diagnostics.extend(
            _binding_compiler_diagnostics(
                model_input=model_input,
                cleaned_sql=analysis.cleaned_sql,
                dialect=dialect,
                diagnostics=analysis.polyglot_analysis.binding_diagnostics,
            )
        )
    return tuple(diagnostics)


def _binding_compiler_diagnostics(
    *,
    model_input: CompileModelInput,
    diagnostics: tuple[SqlBindingDiagnostic, ...],
    dialect: str | None,
    cleaned_sql: str | None = None,
) -> tuple[CompilerDiagnostic, ...]:
    line_offset: int | None = query_line_offset(model_input)
    seen: set[tuple[str, str, int | None, int | None]] = set()
    result: list[CompilerDiagnostic] = []
    for diagnostic in diagnostics:
        if diagnostic.code == BINDING_UNKNOWN_TABLE_INTERNAL_CODE:
            continue
        if cleaned_sql is None:
            cleaned_sql = get_complete_schema_binding_request(
                query_sql=cursor_intrinsics_analysis_sql(
                    sql=model_input.query_sql,
                    cursor_type=model_input.config.values.get("cursor_type"),
                ),
                placeholders=_model_placeholders(model_input),
                dialect=dialect,
                binding_schema={},
            ).sql
        line: int | None
        column: int | None
        location: SourceLocation | None = get_authored_binding_location(
            path=model_input.model_file.relative_path,
            authored_sql=model_input.model_file.contents,
            authored_query_sql=model_input.model_file.query_sql,
            cleaned_sql=cleaned_sql,
            expansion=model_input.sql_expansion,
            diagnostic=diagnostic,
        )
        line, column = (location.line, location.column) if location is not None else (None, None)
        if line is None:
            line = (
                diagnostic.line + line_offset
                if diagnostic.line is not None and line_offset is not None
                else diagnostic.line
            )
            column = diagnostic.column
        key: tuple[str, str, int | None, int | None] = (
            diagnostic.code,
            diagnostic.message,
            line,
            column,
        )
        if key in seen and diagnostic.severity == DiagnosticSeverity.ERROR:
            continue
        seen.add(key)
        result.append(
            CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity(diagnostic.severity),
                code=diagnostic.code,
                message=diagnostic.message,
                resource_type=CompiledResourceType.MODEL,
                resource_name=_model_name(model_input),
                path=model_input.model_file.relative_path,
                line=line,
                column=column,
                location=location,
            )
        )
    return tuple(result)


def _schema_column_nullability(
    columns: tuple[SchemaColumn, ...],
) -> dict[str, InferredNullability]:
    return {
        column.name: _declared_column_nullability(nullable=column.nullable, audits=column.audits)
        for column in columns
    }


def _source_column_nullability(
    columns: tuple[SourceColumnEntry, ...],
) -> dict[str, InferredNullability]:
    return {
        column.name: _declared_column_nullability(nullable=column.nullable, audits=column.audits)
        for column in columns
    }


def _declared_column_nullability(
    *,
    nullable: bool | None,
    audits: tuple[SchemaAuditInstance, ...],
) -> InferredNullability:
    if nullable is False:
        return InferredNullability.NON_NULL
    if any(audit.definition_name == NOT_NULL_AUDIT_NAME for audit in audits):
        return InferredNullability.NON_NULL
    return InferredNullability.UNKNOWN


def _assemble_compiled_source(
    *,
    source_input: CompileSourceInput,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> CompiledSource:
    source_entry: SourceEntry = _build_source_relation_entry(
        source_entry=source_input.source_entry,
        target_config=target_config,
        effective_vars=effective_vars,
    )
    return CompiledSource(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=source_entry.name),
        deps=(),
        name=source_entry.name,
        source_entry=source_entry,
        source_file=source_input.source_file,
    )


def _build_source_relation_entry(
    *,
    source_entry: SourceEntry,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> SourceEntry:
    if source_entry.loader is None or target_config is None:
        return source_entry
    loader_target_config: TargetConfig = replace(
        target_config,
        schema=target_config.loader_schema or target_config.schema,
    )
    validate_preserved_logical_namespace(
        resource_label=f"Managed source '{source_entry.name}'",
        logical_database=source_entry.database,
        logical_schema=source_entry.schema,
        target_config=loader_target_config,
    )
    return replace(
        source_entry,
        database=(
            source_entry.database
            if source_entry.database is not None
            else _expand_target_value(
                value=target_config.database,
                effective_vars=effective_vars,
            )
        ),
        schema=(
            source_entry.schema
            if source_entry.schema is not None
            else _expand_target_value(
                value=target_config.loader_schema or target_config.schema,
                effective_vars=effective_vars,
            )
        ),
    )


def _expand_target_value(*, value: str | None, effective_vars: dict[str, object]) -> str | None:
    if value is None:
        return None
    return str(
        expand_template_data(
            value=value,
            variables=effective_vars,
            context_values={},
            context_label="managed source target",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )


def _assemble_compiled_seed(
    *,
    seed_input: CompileSeedInput,
    defaults: DefaultsConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> CompiledSeed:
    target: CompiledRelationLocation = build_seed_relation_target(
        seed_entry=seed_input.schema_entry,
        defaults=defaults,
        target_config=target_config,
        effective_vars=effective_vars,
    )
    return CompiledSeed(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SEED, name=seed_input.schema_entry.name
        ),
        deps=(),
        name=seed_input.schema_entry.name,
        seed_file=seed_input.seed_file,
        schema_entry=seed_input.schema_entry,
        schema_file=seed_input.schema_file,
        destination=target,
    )


def _assemble_compiled_function(
    *,
    function_input: CompileSqlFunctionInput,
    seed_names: frozenset[str] = frozenset(),
) -> CompiledFunction:
    return CompiledFunction(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType(
                function_node_type(return_columns=function_input.return_columns)
            ),
            name=function_input.name,
        ),
        deps=function_build_deps(references=function_input.references, seed_names=seed_names),
        name=function_input.name,
        relative_path=function_input.function_file.relative_path,
        arguments=function_input.arguments,
        returns=function_input.returns,
        body_sql=function_input.body_sql,
        return_columns=function_input.return_columns,
        references=function_input.references,
        destination=CompiledRelationLocation(
            database=function_input.database,
            schema=function_input.schema,
            name=function_input.name,
            qualified_name=None,
            logical_database=function_input.logical_database,
            logical_schema=function_input.logical_schema,
        ),
        fingerprint_destination=CompiledRelationLocation(
            database=function_input.fingerprint_database,
            schema=function_input.fingerprint_schema,
            name=function_input.name,
            qualified_name=None,
            logical_database=function_input.fingerprint_logical_database,
            logical_schema=function_input.fingerprint_logical_schema,
        ),
        language=function_input.language,
        source_file_path=function_input.function_file.file_path,
        runtime_version=function_input.runtime_version,
        entry_point=function_input.entry_point,
        packages=function_input.packages,
        replay_on_change=function_input.replay_on_change,
        tags=function_input.tags,
    )


def _assemble_compiled_audit(audit_input: CompileAuditInput) -> CompiledAudit:
    audit_name: str = _resolve_audit_name(audit_input)
    normalized_target_kind: AttachedAuditTargetKind | None = None
    if audit_input.attached_target_kind is not None:
        normalized_target_kind = AttachedAuditTargetKind(audit_input.attached_target_kind)
    return CompiledAudit(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=audit_name),
        scope_deps=audit_scope_deps(
            references=audit_input.references,
            attached_target_kind=audit_input.attached_target_kind,
            attached_target_name=audit_input.attached_target_name,
        ),
        name=audit_name,
        definition_name=(audit_input.audit_block.name or audit_input.audit_file.file_path.stem),
        audit_file=audit_input.audit_file,
        audit_block=audit_input.audit_block,
        sql_body=audit_input.sql_body,
        evaluation_mode=audit_input.evaluation_mode,
        measurement_contract=audit_input.measurement_contract,
        thresholds=audit_input.thresholds,
        minimum_samples=audit_input.minimum_samples,
        measure_sql=audit_input.measure_sql,
        evidence_sql=audit_input.evidence_sql,
        evidence_limit=audit_input.evidence_limit,
        references=audit_input.references,
        attached_target_kind=normalized_target_kind,
        attached_target_name=audit_input.attached_target_name,
        attached_column_name=audit_input.attached_column_name,
        severity=audit_input.severity,
        run_scope=audit_input.run_scope,
        always_run=audit_input.always_run,
        description=audit_input.description,
    )


def _assemble_compiled_sql_test(
    *,
    test_input: CompileSqlTestInput,
    model_inputs: tuple[CompileModelInput, ...],
    inputs: CompileProjectInputs,
) -> CompiledSqlTest:
    test_name: str = _resolve_test_name(test_input)
    compiled_payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload
    scope_deps: tuple[CompiledObjectKey, ...]
    if isinstance(test_input.payload, CompileDirectLogicSqlTestInputPayload):
        if test_input.payload.mode == SqlTestMode.MACRO:
            scope_deps = _macro_sql_test_scope_deps(
                tested_macro_names=test_input.payload.tested_resource_names,
                model_inputs=model_inputs,
            )
        elif test_input.payload.mode == SqlTestMode.UDF:
            scope_deps = _udf_sql_test_scope_deps(
                tested_udf_names=test_input.payload.tested_resource_names,
                model_inputs=model_inputs,
            )
        else:
            scope_deps = _function_sql_test_scope_deps(
                tested_function_names=test_input.payload.tested_resource_names,
            )
        compiled_payload = CompiledDirectLogicSqlTestPayload(
            mode=test_input.payload.mode,
            helper_ctes=test_input.payload.helper_ctes,
            actual_cte=test_input.payload.actual_cte,
            expected_cte=test_input.payload.expected_cte,
            tested_resource_names=test_input.payload.tested_resource_names,
        )
    else:
        model_payload: CompileModelSqlTestInputPayload = test_input.payload
        assertion_target_model_names: tuple[str, ...] = extract_assertion_target_model_names(
            assertion_sql=tuple(cte.sql_body for cte in model_payload.assertion_ctes)
        )
        scope_deps = sql_test_scope_deps(
            expected_model_names=tuple(
                dict.fromkeys((*model_payload.expected_model_names, *assertion_target_model_names))
            )
        )
        compiled_payload = CompiledModelSqlTestPayload(
            authored_ctes=model_payload.authored_ctes,
            macro_mocks=model_payload.macro_mocks,
            model_query_overrides=_build_test_model_query_overrides(
                test_input=test_input,
                model_inputs=model_inputs,
                inputs=inputs,
            ),
            mock_model_names=model_payload.mock_model_names,
            mock_source_names=model_payload.mock_source_names,
            mock_seed_names=model_payload.mock_seed_names,
            mock_dbt_ref_names=model_payload.mock_dbt_ref_names,
            mock_table_function_names=model_payload.mock_table_function_names,
            expected_ctes=model_payload.expected_ctes,
            expected_model_names=model_payload.expected_model_names,
            assertion_ctes=model_payload.assertion_ctes,
            assertion_names=model_payload.assertion_names,
        )
    tested_resources: tuple[CompiledSqlTestResource, ...] = (
        tuple(
            CompiledSqlTestResource(kind=test_input.payload.mode, name=name)
            for name in test_input.payload.tested_resource_names
        )
        if isinstance(test_input.payload, CompileDirectLogicSqlTestInputPayload)
        else ()
    )
    case_fingerprint: str | None = (
        build_sql_test_case_fingerprint(
            source_path=test_input.test_file.relative_path,
            block_index=test_input.test_block.test_index,
            case_name=test_input.case_name,
            parameter_schema=test_input.parameter_schema,
            parameter_values=test_input.parameter_values,
            expanded_sql=test_input.sql_body,
            scope_deps=scope_deps,
            tested_resources=tested_resources,
        )
        if test_input.case_name is not None
        else None
    )
    return CompiledSqlTest(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=test_name),
        scope_deps=scope_deps,
        name=test_name,
        test_file=test_input.test_file,
        test_block=test_input.test_block,
        sql_body=test_input.sql_body,
        mode=test_input.mode,
        payload=compiled_payload,
        source_path=test_input.test_file.relative_path,
        ownership_root=test_input.test_file.ownership_root,
        block_index=test_input.test_block.test_index,
        explicit_name=test_input.test_block.name,
        parent_name=test_input.parent_name,
        case_name=test_input.case_name,
        case_index=test_input.case_index,
        case_fingerprint=case_fingerprint,
        parameter_schema=test_input.parameter_schema,
        parameter_values=test_input.parameter_values,
        expected_model_names=(
            test_input.payload.expected_model_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        assertion_names=(
            test_input.payload.assertion_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        assertion_target_model_names=(
            assertion_target_model_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        target_model_names=(
            tuple(
                dict.fromkeys(
                    (*test_input.payload.expected_model_names, *assertion_target_model_names)
                )
            )
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        tested_resources=tested_resources,
    )


def _macro_sql_test_scope_deps(
    *, tested_macro_names: tuple[str, ...], model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompiledObjectKey, ...]:
    tested_names: frozenset[str] = frozenset(tested_macro_names)
    scope_deps: list[CompiledObjectKey] = []
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_macro_deps: frozenset[str] = frozenset(
            model_input.macro_deps or find_macro_call_names(model_input.macro_source_sql)
        )
        if not tested_names.intersection(model_macro_deps):
            continue
        scope_deps.append(
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL,
                name=model_input.model_file.file_path.stem,
            )
        )
    return tuple(scope_deps)


def _udf_sql_test_scope_deps(
    *, tested_udf_names: tuple[str, ...], model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompiledObjectKey, ...]:
    tested_names: frozenset[str] = frozenset(tested_udf_names)
    scope_deps: list[CompiledObjectKey] = []
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_udf_deps: frozenset[str] = frozenset(
            reference.ref_name
            for reference in model_input.references
            if reference.ref_kind == SqlReferenceKind.UDF
        )
        if not tested_names.intersection(model_udf_deps):
            continue
        scope_deps.append(
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL,
                name=model_input.model_file.file_path.stem,
            )
        )
    return tuple(scope_deps)


def _function_sql_test_scope_deps(
    *, tested_function_names: tuple[str, ...]
) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        CompiledObjectKey(resource_type=CompiledResourceType.TABLE_FN, name=function_name)
        for function_name in tested_function_names
    )


def _build_test_model_query_overrides(
    *,
    test_input: CompileSqlTestInput,
    model_inputs: tuple[CompileModelInput, ...],
    inputs: CompileProjectInputs,
) -> dict[str, str]:
    """Re-expand each model from its pre-macro macro_source_sql with test macro mocks applied."""

    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return {}
    if not test_input.payload.macro_mocks:
        return {}
    macro_context: MacroContext = inputs.macro_context or MacroContext(
        adapter_name=resolve_effective_adapter_name(
            project_config=inputs.project_config,
            local_config=inputs.local_config,
        ),
        sql_analysis_enabled=inputs.effective_settings.sql_analysis,
        target_name=inputs.effective_target_name,
        vars=inputs.effective_vars,
    )
    overrides: dict[str, str] = {}
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_name: str = model_input.model_file.file_path.stem
        macro_source_sql: str = model_input.macro_source_sql or model_input.query_sql
        overrides[model_name] = get_validated_model_cursor_intrinsics(
            sql=expand_sql_macros(
                sql=macro_source_sql,
                file_path=model_input.model_file.file_path,
                loaded_macros=inputs.loaded_macros,
                macro_overrides=test_input.payload.macro_mocks,
                macro_context=macro_context,
                declaration_resolver=(
                    build_declaration_scope_resolver(
                        discovered_inputs=inputs.discovered_inputs,
                        scope_index=inputs.scope_index,
                        loaded_macros=inputs.loaded_macros,
                    )
                ),
            ),
            config_values=model_input.config.values,
            model_name=model_name,
        )
    return overrides


def _assemble_compiled_sql_scenario(
    scenario_input: CompileSqlScenarioInput,
) -> CompiledSqlScenario:
    scenario_name: str = scenario_input.scenario_file.name
    return CompiledSqlScenario(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=scenario_name,
        ),
        name=scenario_name,
        scenario_file=scenario_input.scenario_file,
        sql_body=scenario_input.sql_body,
        authored_ctes=scenario_input.authored_ctes,
        expected_ctes=scenario_input.expected_ctes,
        assertion_ctes=scenario_input.assertion_ctes,
        source_fixture_names=scenario_input.source_fixture_names,
        ref_fixture_names=scenario_input.ref_fixture_names,
        seed_fixture_names=scenario_input.seed_fixture_names,
        dbt_ref_fixture_names=scenario_input.dbt_ref_fixture_names,
        expected_model_names=scenario_input.expected_model_names,
        assertion_names=scenario_input.assertion_names,
        assertion_target_model_names=scenario_input.assertion_target_model_names,
        target_model_names=scenario_input.target_model_names,
        source_path=scenario_input.scenario_file.relative_path,
        ownership_root=scenario_input.scenario_file.ownership_root,
    )


def _resolve_audit_name(audit_input: CompileAuditInput) -> str:
    if audit_input.name is not None:
        return audit_input.name
    if audit_input.audit_block.name is not None:
        return audit_input.audit_block.name
    return audit_input.audit_file.file_path.stem


def _resolve_test_name(test_input: CompileSqlTestInput) -> str:
    parent_name: str = test_input.test_block.name or test_input.test_file.file_path.stem
    if test_input.case_name is not None:
        return f"{parent_name} [{test_input.case_name}]"
    return parent_name
