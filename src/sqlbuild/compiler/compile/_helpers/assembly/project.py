"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile._helpers.analysis.cache import (
    build_analysis_cache_context,
)
from sqlbuild.compiler.compile._helpers.analysis.compact import (
    analyze_columns_and_lineage_with_polyglot,
    get_complete_schema_binding_request,
    infer_columns_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import (
    model_placeholders as _model_placeholders,
)
from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_hook_sql_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile._helpers.assembly.binding_positions import (
    get_authored_binding_location,
    query_line_offset,
)
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    build_column_nullability_by_table,
    build_complete_binding_schemas,
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
from sqlbuild.compiler.compile._helpers.diagnostics.scope import report_scope_index_errors
from sqlbuild.compiler.compile._helpers.native_stages.assembly import (
    analyze_model_sql,
    expression_source_shapes_by_engine,
    project_facts_by_engine,
)
from sqlbuild.compiler.compile._helpers.native_stages.sql_tests import (
    assemble_sql_tests_by_engine,
)
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    resolve_early_model_templates,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
)
from sqlbuild.compiler.compile._helpers.render.declarations import build_declaration_scope_resolver
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    find_macro_call_names,
)
from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile._helpers.sql_tests.helper_ctes import (
    report_mocks_reading_referencing_helpers,
)
from sqlbuild.compiler.compile._helpers.sql_tests.identity import build_sql_test_case_fingerprint
from sqlbuild.compiler.compile._helpers.sql_tests.scope_deps import (
    function_sql_test_scope_deps,
    macro_sql_test_scope_deps,
    udf_sql_test_scope_deps,
)
from sqlbuild.compiler.compile.main._scope_index_with_compile_usages import (
    scope_index_with_compile_usages,
)
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
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
    DeclarationScopeResolver,
    DynamicColumnContractProof,
    InferredColumn,
    MacroContext,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysis as _ModelSqlAnalysis,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    SqlTestMode,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.profiling.main._record_cpu import record_compile_cpu_timing
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.project_assembly.models import (
    NativeModelFacts,
    NativeProjectFacts,
    NativeProjectResources,
)
from sqlbuild.compiler.resource_names.main.function_node_type import function_node_type
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.sql_analysis.constants import (
    BINDING_UNKNOWN_TABLE_INTERNAL_CODE,
    NATIVE_DIALECT_ALIASES,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._identifier_case import ignores_quoted_case
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
)
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    SchemaDynamicColumnFamily,
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
        build_column_nullability_by_table(inputs)
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
        expression_sources: tuple[CompileSourceInput, ...] = tuple(
            source_input
            for source_input in inputs.source_inputs
            if source_input.source_entry.expression
        )
        expression_shapes: tuple[dict[str, str] | None, ...] = expression_source_shapes_by_engine(
            expressions=tuple(
                cast(str, source_input.source_entry.expression)
                for source_input in expression_sources
            ),
            profile=profile,
        )
        for source_input, shape in zip(expression_sources, expression_shapes, strict=True):
            if shape is not None:
                declared_types: dict[str, str] = column_types_by_table.get(
                    source_input.source_entry.name, {}
                )
                declared_shape: dict[str, str] = {
                    name: declared_types.get(name, column_type)
                    for name, column_type in shape.items()
                }
                complete_binding_schemas[source_input.source_entry.name] = declared_shape
                column_types_by_table[source_input.source_entry.name] = declared_shape
                column_nullability_by_table[source_input.source_entry.name] = {
                    name: column_nullability_by_table.get(source_input.source_entry.name, {}).get(
                        name, InferredNullability.UNKNOWN
                    )
                    for name in declared_shape
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
    native_session: Any | None = None
    if sql_analysis_enabled:
        with (
            record_compile_timing("model_analysis_ms"),
            record_compile_cpu_timing("model_analysis_cpu_ms"),
        ):
            model_sql_analysis_by_name, native_session = analyze_model_sql(
                NativeModelAnalysisRequest(
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
                    dynamic_families_by_table=dynamic_families_by_table,
                )
            )
    native: NativeProjectFacts | None = project_facts_by_engine(
        inputs=inputs,
        dialect=profile.sql_analysis_dialect,
        analysis_model_names=analysis_model_names,
        analyses=model_sql_analysis_by_name,
        session=native_session,
        column_types_by_table=column_types_by_table,
        authoritative_column_types_by_table=complete_binding_schemas,
        column_nullability_by_table=column_nullability_by_table,
        dynamic_families_by_table=dynamic_families_by_table,
    )
    resources: NativeProjectResources | None = native.resources if native else None
    scope_index: ScopeIndex = scope_index_with_compile_usages(inputs=inputs)
    report_scope_index_errors(index=scope_index)
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
        sql_lexical_syntax=inputs.sql_lexical_syntax,
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
                native_model=native.models[index] if native else None,
                column_nullability_by_table=column_nullability_by_table,
                column_types_by_table=column_types_by_table,
                dynamic_contract_analysis_inputs=dynamic_contract_analysis_inputs,
                inference_profile=profile,
                sql_analysis=model_sql_analysis_by_name.get(model_input.model_file.file_path.stem),
                allow_compact_analysis=allow_compact_analysis,
            )
            for index, model_input in enumerate(inputs.model_inputs)
        ),
        sources=tuple(
            _assemble_compiled_source(
                source_input=source_input,
                target_config=inputs.effective_target,
                effective_vars=inputs.effective_vars,
                native_entry=resources.source_entries[index] if resources else None,
            )
            for index, source_input in enumerate(inputs.source_inputs)
        ),
        seeds=tuple(
            _assemble_compiled_seed(
                seed_input=seed_input,
                defaults=inputs.project_config.defaults,
                target_config=inputs.effective_target,
                effective_vars=inputs.effective_vars,
                native_destination=resources.seed_destinations[index] if resources else None,
            )
            for index, seed_input in enumerate(inputs.seed_inputs)
        ),
        functions=tuple(
            _assemble_compiled_function(
                function_input=function_input,
                seed_names=seed_names,
                native_deps=resources.function_deps[index] if resources else None,
            )
            for index, function_input in enumerate(inputs.sql_function_inputs)
        ),
        audits=tuple(
            _assemble_compiled_audit(
                audit_input=audit_input,
                native_scope_deps=resources.audit_scope_deps[index] if resources else None,
            )
            for index, audit_input in enumerate(inputs.audit_inputs)
        ),
        sql_tests=assemble_sql_tests_by_engine(
            inputs=inputs,
            assemble_python_test=lambda test_input: _assemble_compiled_sql_test(
                test_input=test_input, model_inputs=inputs.model_inputs, inputs=inputs
            ),
        ),
        sql_scenarios=tuple(
            _assemble_compiled_sql_scenario(scenario_input)
            for scenario_input in inputs.scenario_inputs
        ),
        loader_functions=inputs.discovered_inputs.loader_functions,
        hook_functions=inputs.discovered_inputs.hook_functions,
        enforce_explicit_references=inputs.project_config.references.enforce_explicit,
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
        resource_sql_analysis=sql_analysis_enabled and not inputs.no_sql_validation,
        native_session=native_session,
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
    native_model: NativeModelFacts | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    column_types_by_table: dict[str, dict[str, str]] | None = None,
    dynamic_contract_analysis_inputs: _DynamicContractAnalysisInputs | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
    sql_analysis: _ModelSqlAnalysis | None = None,
    allow_compact_analysis: bool = False,
) -> CompiledModel:
    model_name: str = model_input.model_file.file_path.stem
    native_deps: tuple[CompiledObjectKey, ...] | None = native_model.deps if native_model else None
    syntax_validated: bool = native_model is not None and native_model.syntax_valid
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
    if sql_validation_enabled and model_input.sql_validation_enabled and not syntax_validated:
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
            if model_input.sql_validation_enabled and not syntax_validated:
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
    elif sql_validation_enabled and model_input.sql_validation_enabled and not syntax_validated:
        validate_sql_syntax(
            query_sql=analysis_query_sql,
            model_name=model_name,
            file_path=model_input.model_file.file_path,
            placeholders=placeholders,
            dialect=profile.sql_analysis_dialect,
        )
    dynamic_column_contract: DynamicColumnContractProof | None = (
        sql_analysis.dynamic_column_contract
        if sql_analysis is not None and sql_analysis.dynamic_column_contract is not None
        else native_model.dynamic_contract
        if native_model is not None
        else None
    )
    if dynamic_column_contract is not None and dynamic_column_contract.output_proven:
        inferred_columns = dynamic_column_contract.fixed_columns
        fast_lineage_has_star = True
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
        deps=(
            native_deps
            if native_deps is not None
            else model_build_deps(references=model_input.references)
        ),
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
        rejected_sql_analysis_opt_out=model_input.rejected_sql_analysis_opt_out,
    )


def _model_name(model_input: CompileModelInput) -> str:
    return model_input.model_file.file_path.stem


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
        if (
            key in seen
            and diagnostic.start is not None
            and diagnostic.severity == DiagnosticSeverity.ERROR
        ):
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


def _assemble_compiled_source(
    *,
    source_input: CompileSourceInput,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
    native_entry: SourceEntry | None = None,
) -> CompiledSource:
    source_entry: SourceEntry = (
        native_entry
        if native_entry is not None
        else _build_source_relation_entry(
            source_entry=source_input.source_entry,
            target_config=target_config,
            effective_vars=effective_vars,
        )
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
    native_destination: CompiledRelationLocation | None = None,
) -> CompiledSeed:
    target: CompiledRelationLocation = (
        native_destination
        if native_destination is not None
        else build_seed_relation_target(
            seed_entry=seed_input.schema_entry,
            defaults=defaults,
            target_config=target_config,
            effective_vars=effective_vars,
        )
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
    native_deps: tuple[CompiledObjectKey, ...] | None = None,
) -> CompiledFunction:
    return CompiledFunction(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType(
                function_node_type(return_columns=function_input.return_columns)
            ),
            name=function_input.name,
        ),
        deps=(
            native_deps
            if native_deps is not None
            else function_build_deps(references=function_input.references, seed_names=seed_names)
        ),
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
        tags=function_input.tags,
        description=function_input.description,
    )


def _assemble_compiled_audit(
    *,
    audit_input: CompileAuditInput,
    native_scope_deps: tuple[CompiledObjectKey, ...] | None = None,
) -> CompiledAudit:
    audit_name: str = _resolve_audit_name(audit_input)
    normalized_target_kind: AttachedAuditTargetKind | None = None
    if audit_input.attached_target_kind is not None:
        normalized_target_kind = AttachedAuditTargetKind(audit_input.attached_target_kind)
    return CompiledAudit(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=audit_name),
        scope_deps=(
            native_scope_deps
            if native_scope_deps is not None
            else audit_scope_deps(
                references=audit_input.references,
                attached_target_kind=audit_input.attached_target_kind,
                attached_target_name=audit_input.attached_target_name,
            )
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
    target_model_names: tuple[str, ...] = ()
    if isinstance(test_input.payload, CompileDirectLogicSqlTestInputPayload):
        if test_input.payload.mode == SqlTestMode.MACRO:
            scope_deps = macro_sql_test_scope_deps(
                tested_macro_names=test_input.payload.tested_resource_names,
                model_inputs=model_inputs,
            )
        elif test_input.payload.mode == SqlTestMode.UDF:
            scope_deps = udf_sql_test_scope_deps(
                tested_udf_names=test_input.payload.tested_resource_names,
                model_inputs=model_inputs,
            )
        else:
            scope_deps = function_sql_test_scope_deps(
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
        target_model_names = tuple(
            dict.fromkeys(
                (
                    *model_payload.expected_model_names,
                    *model_payload.assertion_target_model_names,
                    *model_payload.reference_target_model_names,
                )
            )
        )
        report_mocks_reading_referencing_helpers(
            authored_ctes=model_payload.authored_ctes,
            reader_ctes=(*model_payload.expected_ctes, *model_payload.assertion_ctes),
            model_inputs=model_inputs,
            target_model_names=target_model_names,
            mock_model_names=model_payload.mock_model_names,
            test_file=test_input.test_file,
            test_block=test_input.test_block,
            syntax=inputs.sql_lexical_syntax,
        )
        scope_deps = sql_test_scope_deps(expected_model_names=target_model_names)
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
            test_input.payload.assertion_target_model_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        read_helper_names=(
            test_input.payload.read_helper_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        reference_target_model_names=(
            test_input.payload.reference_target_model_names
            if isinstance(test_input.payload, CompileModelSqlTestInputPayload)
            else ()
        ),
        target_model_names=target_model_names,
        tested_resources=tested_resources,
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
    model_macro_context: MacroContext = inputs.macro_context or MacroContext(
        adapter_name=resolve_effective_adapter_name(
            project_config=inputs.project_config,
            local_config=inputs.local_config,
        ),
        sql_analysis_enabled=inputs.effective_settings.sql_analysis,
        target_name=inputs.effective_target_name,
        vars=inputs.effective_vars,
    )
    macro_context: MacroContext = replace(model_macro_context, _enforce_explicit_references=False)
    declaration_resolver: DeclarationScopeResolver = build_declaration_scope_resolver(
        discovered_inputs=inputs.discovered_inputs,
        scope_index=inputs.scope_index,
        loaded_macros=inputs.loaded_macros,
        lookup=(
            inputs.declaration_scope.resolver.lookup
            if inputs.declaration_scope is not None
            else None
        ),
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
                declaration_resolver=declaration_resolver,
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
