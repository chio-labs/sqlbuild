"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.analysis_session.main._infer_native_query_column_rows import (
    infer_native_query_column_rows,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeColumnQuery,
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
)
from sqlbuild.compiler.analysis_session.types import ColumnRow, DiagnosticRow
from sqlbuild.compiler.compile._helpers.analysis.cache import (
    build_analysis_cache_context,
)
from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import (
    model_placeholders as _model_placeholders,
)
from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_hook_sql_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile._helpers.assembly.hand_built_models import (
    hand_built_compiled_model,
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
from sqlbuild.compiler.compile.main._scope_index_with_compile_usages import (
    scope_index_with_compile_usages,
)
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlScenario,
    CompileModelSqlTestInputPayload,
    CompilerDiagnostic,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
    DeclarationScopeResolver,
    HandBuiltAnalysis,
    MacroContext,
)
from sqlbuild.compiler.compile.types import (
    CompiledAuditView,
    CompiledFunctionView,
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
    CompiledSeedView,
    CompiledSourceView,
    CompileInputsView,
    ModelInput,
    SourceInput,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.profiling.main._record_cpu import record_compile_cpu_timing
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.project_assembly.constants import AUDIT_SLOT, SEED_SLOT, SOURCE_SLOT
from sqlbuild.compiler.project_assembly.main._native_resource import native_resource
from sqlbuild.compiler.project_assembly.models import (
    NativeModelFacts,
    NativeProjectFacts,
    NativeProjectResources,
)
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.sql_analysis.constants import (
    NATIVE_DIALECT_ALIASES,
    NATIVE_FAILURE_PREFIX,
)
from sqlbuild.compiler.sql_analysis.main._binding_catalog import create_binding_catalog
from sqlbuild.compiler.sql_analysis.main._identifier_case import ignores_quoted_case
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_scenario_config import (
    resolve_effective_scenario_config,
)
from sqlbuild.spec.contracts.models import (
    SchemaDynamicColumnFamily,
)


@dataclass(frozen=True)
class _DynamicContractAnalysisInputs:
    families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]]
    authoritative_column_types_by_table: dict[str, dict[str, str]]


def assemble_compiled_project(
    *,
    inputs: CompileInputsView,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProjectView:
    """Convert attached compile inputs into the planner-ready project view."""

    sql_analysis_enabled: bool = (
        inputs.effective_settings.sql_analysis and not skip_column_inference
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
        expression_sources: tuple[SourceInput, ...] = tuple(
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
    analyses: NativeModelAnalyses | None = None
    if sql_analysis_enabled:
        with (
            record_compile_timing("model_analysis_ms"),
            record_compile_cpu_timing("model_analysis_cpu_ms"),
        ):
            analyses = analyze_model_sql(
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
    native_session: Any | None = None if analyses is None else analyses.session
    native: NativeProjectFacts = project_facts_by_engine(
        inputs=inputs,
        dialect=profile.sql_analysis_dialect,
        analysis_model_names=analysis_model_names,
        analyses=analyses,
        session=native_session,
        column_types_by_table=column_types_by_table,
        authoritative_column_types_by_table=complete_binding_schemas,
        column_nullability_by_table=column_nullability_by_table,
        dynamic_families_by_table=dynamic_families_by_table,
    )
    resources: NativeProjectResources = native.resources
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
    models: tuple[CompiledModelView, ...] = tuple(
        _assemble_compiled_model(
            model_input=model_input,
            sql_analysis_enabled=(
                sql_analysis_enabled
                and model_input.sql_validation_enabled
                and (
                    analysis_model_names is None or _model_name(model_input) in analysis_model_names
                )
            ),
            sql_validation_enabled=(
                analysis_model_names is None or _model_name(model_input) in analysis_model_names
            ),
            native_model=native.models[index],
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            dynamic_contract_analysis_inputs=dynamic_contract_analysis_inputs,
            inference_profile=profile,
            analyses=analyses,
            allow_compact_analysis=allow_compact_analysis,
        )
        for index, model_input in enumerate(inputs.model_inputs)
    )
    fields: dict[str, Any] = dict(
        binding_catalog=profile.binding_catalog,
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
        models=models,
        sources=_compiled_sources(inputs=inputs, resources=resources),
        seeds=_compiled_seeds(inputs=inputs, resources=resources),
        functions=_compiled_functions(inputs=inputs, resources=resources),
        audits=_compiled_audits(inputs=inputs, resources=resources),
        sql_tests=assemble_sql_tests_by_engine(
            inputs=inputs,
            macro_mock_queries=lambda test_input: _build_test_model_query_overrides(
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
            *_project_binding_diagnostics(models=models, analyses=analyses),
        ),
        external_sql_reference_resolver=inputs.external_sql_reference_resolver,
        scope_index=scope_index,
    )
    project: CompiledProjectView = _assembled_project(inputs=inputs, fields=fields)
    return complete_semantic_diagnostics(
        project=project,
        profile=profile,
        resource_sql_analysis=sql_analysis_enabled and not inputs.no_sql_validation,
        native_session=native_session,
        binding_results=_binding_rows(analyses),
    )


def _assembled_project(*, inputs: CompileInputsView, fields: dict[str, Any]) -> CompiledProjectView:
    """The native owner's project view when it holds every model; else a `CompiledProject`."""

    models: tuple[CompiledModelView, ...] = fields["models"]
    if inputs.native_project is not None and all(
        isinstance(model, _native.NativeCompiledModel) for model in models
    ):
        return inputs.native_project.project_view(
            {**fields, "unmatched_literal_sql_relations": (), "native_session": None}
        )
    return CompiledProject(
        **fields,
        sql_expansions={
            model_input.model_file.file_path: model_input.sql_expansion
            for model_input in inputs.model_inputs
            if model_input.sql_expansion is not None
        },
    )


def _str_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _connection_database_fallback(*, inputs: CompileInputsView) -> str | None:
    adapter_name: str = resolve_effective_adapter_name(
        project_config=inputs.project_config,
        local_config=inputs.local_config,
    )
    if adapter_name == BuiltinAdapter.DUCKDB:
        return None
    return _str_or_none(inputs.effective_connection.get("database"))


def _assemble_compiled_model(
    *,
    model_input: ModelInput,
    sql_analysis_enabled: bool,
    sql_validation_enabled: bool = True,
    native_model: NativeModelFacts,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    column_types_by_table: dict[str, dict[str, str]] | None = None,
    dynamic_contract_analysis_inputs: _DynamicContractAnalysisInputs | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
    analyses: NativeModelAnalyses | None = None,
    allow_compact_analysis: bool = False,
) -> CompiledModelView:
    del column_types_by_table, dynamic_contract_analysis_inputs, allow_compact_analysis
    model_name: str = model_input.model_file.file_path.stem
    syntax_validated: bool = native_model.syntax_valid
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    analysis_query_sql: str = cursor_intrinsics_analysis_sql(
        sql=model_input.query_sql,
        cursor_type=model_input.config.values.get("cursor_type"),
    )
    placeholders: dict[str, str] | None = _model_placeholders(model_input)
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
    session_analysis: tuple[_native.NativeModelAnalysisSession, int] | None = None
    fallback: list[ColumnRow] | None = None
    if sql_analysis_enabled:
        position: int | None = None if analyses is None else analyses.positions.get(model_name)
        if analyses is None or position is None:
            raise _native.NativeCompilerError(
                f"{NATIVE_FAILURE_PREFIX}native model analysis: the session returned no "
                f"analysis for model '{model_name}'"
            )
        session_analysis = (
            cast(_native.NativeModelAnalysisSession, analyses.session),
            position,
        )
        if model_name not in analyses.succeeded:
            if model_input.sql_validation_enabled and not syntax_validated:
                validate_sql_syntax(
                    query_sql=analysis_query_sql,
                    model_name=model_name,
                    file_path=model_input.model_file.file_path,
                    placeholders=placeholders,
                    dialect=profile.sql_analysis_dialect,
                )
            fallback = infer_native_query_column_rows(
                queries=(
                    NativeColumnQuery(
                        sql=analysis_query_sql, mode="parse", placeholders=placeholders
                    ),
                ),
                profile=profile,
                column_nullability_by_table=column_nullability_by_table,
            )[0][1]
    elif sql_validation_enabled and model_input.sql_validation_enabled and not syntax_validated:
        validate_sql_syntax(
            query_sql=analysis_query_sql,
            model_name=model_name,
            file_path=model_input.model_file.file_path,
            placeholders=placeholders,
            dialect=profile.sql_analysis_dialect,
        )
    macro_deps: tuple[str, ...] = model_input.macro_deps or find_macro_call_names(
        model_input.macro_source_sql
    )
    if isinstance(model_input, _native.NativeModelInput):
        return model_input.compiled_model(
            (
                native_model.deps,
                session_analysis,
                fallback,
                native_model.dynamic_contract,
                list(macro_deps),
            )
        )
    return hand_built_compiled_model(
        model_input=model_input,
        deps=native_model.deps,
        analysis=HandBuiltAnalysis(
            session=session_analysis,
            fallback=fallback,
            standalone_proof=native_model.dynamic_contract,
        ),
        macro_deps=macro_deps,
    )


def _model_name(model_input: ModelInput) -> str:
    return model_input.model_file.file_path.stem


def _build_dynamic_families_by_table(
    inputs: CompileInputsView,
) -> dict[str, tuple[SchemaDynamicColumnFamily, ...]]:
    return {
        model_input.schema_entry.name: model_input.schema_entry.dynamic_columns
        for model_input in inputs.model_inputs
        if model_input.config.values.get("contract") == ContractPolicy.ENFORCED
        and model_input.schema_entry is not None
        and model_input.schema_entry.dynamic_columns
    }


def _project_binding_diagnostics(
    *, models: tuple[CompiledModelView, ...], analyses: NativeModelAnalyses | None
) -> tuple[CompilerDiagnostic, ...]:
    """Every analysed model's located binding diagnostics, which the project also reports."""

    if analyses is None:
        return ()
    diagnostics: list[CompilerDiagnostic] = []
    for model in models:
        if model.name in analyses.positions:
            diagnostics.extend(model.binding_diagnostics)
    return tuple(diagnostics)


def _binding_rows(analyses: NativeModelAnalyses | None) -> dict[str, list[DiagnosticRow]]:
    """Each analysed model's raw binding rows, which semantic type recovery identifies."""

    if analyses is None or analyses.session is None:
        return {}
    rows: list[list[DiagnosticRow]] = analyses.session.binding_rows()
    return {name: rows[position] for name, position in analyses.positions.items()}


def _compiled_sources(
    *, inputs: CompileInputsView, resources: NativeProjectResources
) -> tuple[CompiledSourceView, ...]:
    """Each source's view over the compile's native project, raising assembly's error there."""

    if not inputs.source_inputs:
        return ()
    owner: _native.NativeCompiledProject = cast(
        _native.NativeCompiledProject, inputs.native_project
    )
    owner.record_source_namespaces(list(resources.source_namespaces))
    sources: list[CompiledSourceView] = []
    for index in range(len(inputs.source_inputs)):
        _ = native_resource(
            resources=resources, slot=SOURCE_SLOT, items=resources.source_namespaces, index=index
        )
        sources.append(owner.compiled_source(index))
    return tuple(sources)


def _compiled_seeds(
    *, inputs: CompileInputsView, resources: NativeProjectResources
) -> tuple[CompiledSeedView, ...]:
    """Each seed's view over the compile's native project, raising assembly's error at its seed."""

    if not inputs.seed_inputs:
        return ()
    owner: _native.NativeCompiledProject = cast(
        _native.NativeCompiledProject, inputs.native_project
    )
    owner.record_seed_namespaces(list(resources.seed_namespaces))
    seeds: list[CompiledSeedView] = []
    for index in range(len(inputs.seed_inputs)):
        _ = native_resource(
            resources=resources, slot=SEED_SLOT, items=resources.seed_namespaces, index=index
        )
        seeds.append(owner.compiled_seed(index))
    return tuple(seeds)


def _compiled_functions(
    *, inputs: CompileInputsView, resources: NativeProjectResources
) -> tuple[CompiledFunctionView, ...]:
    """Each function's view over the compile's native project, with its resolved deps."""

    if not inputs.sql_function_inputs:
        return ()
    owner: _native.NativeCompiledProject = cast(
        _native.NativeCompiledProject, inputs.native_project
    )
    owner.record_function_deps(list(resources.function_deps))
    return tuple(owner.compiled_function(index) for index in range(len(inputs.sql_function_inputs)))


def _compiled_audits(
    *, inputs: CompileInputsView, resources: NativeProjectResources
) -> tuple[CompiledAuditView, ...]:
    """Each audit's view over the compile's native project, raising assembly's error there."""

    if not inputs.audit_inputs:
        return ()
    owner: _native.NativeCompiledProject = cast(
        _native.NativeCompiledProject, inputs.native_project
    )
    owner.record_audit_scope_deps(list(resources.audit_scope_deps))
    audits: list[CompiledAuditView] = []
    for index in range(len(inputs.audit_inputs)):
        _ = native_resource(
            resources=resources, slot=AUDIT_SLOT, items=resources.audit_scope_deps, index=index
        )
        audits.append(owner.compiled_audit(index))
    return tuple(audits)


def _build_test_model_query_overrides(
    *,
    test_input: CompileSqlTestInput,
    model_inputs: tuple[ModelInput, ...],
    inputs: CompileInputsView,
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
    model_input: ModelInput
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
