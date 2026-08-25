"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile._helpers.analysis.cache import (
    build_analysis_cache_context,
    model_analysis_cache_key,
    model_analysis_output_signature,
    read_model_analyses,
    write_model_analyses,
)
from sqlbuild.compiler.compile._helpers.analysis.columns import (
    analyze_columns_and_lineage_with_polyglot,
    infer_columns_with_sql_analysis,
    table_function_analysis_name,
)
from sqlbuild.compiler.compile._helpers.analysis.validation import validate_sql_syntax
from sqlbuild.compiler.compile._helpers.deps.dependencies import (
    audit_scope_deps,
    function_build_deps,
    model_build_deps,
    sql_test_scope_deps,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros,
    find_macro_call_names,
)
from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile.constants import NOT_NULL_AUDIT_NAME, PRESERVE_TARGET_VALUE
from sqlbuild.compiler.compile.main.function_node_type import function_node_type
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
    CompileModelInput,
    CompileModelSqlTestInputPayload,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlScenarioInput,
    CompileSqlTestCte,
    CompileSqlTestInput,
    InferredColumn,
    MacroContext,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    SqlTestMode,
)
from sqlbuild.compiler.discovery.main._model_output_column_locations import (
    extract_model_output_column_locations,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode, InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind
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
    SchemaSeedEntry,
    SourceColumnEntry,
    SourceEntry,
    SourceLocation,
    TargetConfig,
)

_POLYGLOT_ANALYSIS_WORKERS: int = 2
_POLYGLOT_PARALLEL_ANALYSIS_MIN_MODELS: int = 32
_POLYGLOT_PARALLEL_REANALYSIS_MIN_MODELS: int = 2


@dataclass(frozen=True)
class _ModelSqlAnalysis:
    polyglot_analysis: PolyglotAnalysisResult
    placeholders: dict[str, str] | None


@dataclass(frozen=True)
class _ModelSqlAnalysisRequest:
    model_input: CompileModelInput
    query_sql: str
    placeholders: dict[str, str] | None
    cache_key: str | None


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
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    allow_compact_analysis: bool = column_lineage_mode == ColumnLineageMode.RICH
    analysis_cache: AnalysisCacheContext | None = (
        build_analysis_cache_context(
            root=analysis_cache_dir,
            inference_profile=profile,
            allow_compact_analysis=allow_compact_analysis,
            signature_namespace={
                "target": inputs.effective_target_name,
                "vars": inputs.effective_vars,
            },
        )
        if sql_analysis_enabled and analysis_model_names != frozenset()
        else None
    )
    model_sql_analysis_by_name: dict[str, _ModelSqlAnalysis] = {}
    if sql_analysis_enabled:
        model_sql_analysis_by_name = _analyze_model_sql_in_parallel(
            model_inputs=tuple(
                model_input
                for model_input in inputs.model_inputs
                if analysis_model_names is None or _model_name(model_input) in analysis_model_names
            ),
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            inference_profile=profile,
            allow_compact_analysis=allow_compact_analysis,
            analysis_cache=analysis_cache,
        )
    return CompiledProject(
        run_id=inputs.run_id,
        effective_target_name=inputs.effective_target_name,
        effective_connection=inputs.effective_connection,
        effective_vars=inputs.effective_vars,
        effective_target_database=(
            (inputs.effective_target.database if inputs.effective_target is not None else None)
            or _connection_database_fallback(inputs=inputs)
        ),
        effective_target_schema=(
            (inputs.effective_target.schema if inputs.effective_target is not None else None)
            or _str_or_none(inputs.effective_connection.get("schema"))
        ),
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
        materialization_files=inputs.discovered_inputs.materialization_files,
        public_enums=inputs.public_enums,
        public_constants=inputs.public_constants,
        diagnostics=inputs.diagnostics,
        external_sql_reference_resolver=inputs.external_sql_reference_resolver,
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
    inference_profile: ExpressionInferenceProfile | None = None,
    sql_analysis: _ModelSqlAnalysis | None = None,
    allow_compact_analysis: bool = False,
) -> CompiledModel:
    model_name: str = model_input.model_file.file_path.stem
    analysis_query_sql: str = cursor_intrinsics_analysis_sql(
        sql=model_input.query_sql,
        cursor_type=model_input.config.values.get("cursor_type"),
    )
    inferred_columns: tuple[InferredColumn, ...] | None = None
    fast_lineage_columns: tuple[CompiledLineageColumnFact, ...] | None = None
    fast_lineage_has_star: bool = False
    placeholders: dict[str, str] | None = (
        sql_analysis.placeholders if sql_analysis is not None else _model_placeholders(model_input)
    )
    if sql_analysis_enabled:
        profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
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
        profile = inference_profile or ExpressionInferenceProfile()
        validate_sql_syntax(
            query_sql=analysis_query_sql,
            model_name=model_name,
            file_path=model_input.model_file.file_path,
            placeholders=placeholders,
            dialect=profile.sql_analysis_dialect,
        )
    output_column_locations: dict[str, SourceLocation] = (
        model_input.model_file.output_column_locations
    )
    if (
        not model_input.model_file.output_column_locations_extracted
        and inferred_columns is not None
        and model_input.schema_entry is not None
        and model_input.schema_entry.columns
    ):
        output_column_locations = extract_model_output_column_locations(
            contents=model_input.model_file.contents,
            relative_path=model_input.model_file.relative_path,
            extract_implicit_alias_columns=(model_input.model_file.extract_implicit_alias_columns),
        )
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
        deps=model_build_deps(references=model_input.references, seed_names=seed_names),
        name=model_name,
        relative_path=model_input.model_file.relative_path,
        query_sql=model_input.query_sql,
        config=model_input.config,
        destination=_build_model_relation_target(model_input=model_input, model_name=model_name),
        references=model_input.references,
        schema_entry=model_input.schema_entry,
        inferred_columns=inferred_columns,
        fast_lineage_columns=fast_lineage_columns,
        fast_lineage_has_star=fast_lineage_has_star,
        authored_sql=model_input.model_file.contents,
        output_column_locations=output_column_locations,
        macro_deps=find_macro_call_names(model_input.macro_source_sql),
        enum_declarations=model_input.enum_declarations,
        constant_declarations=model_input.constant_declarations,
        enum_columns=model_input.enum_columns,
    )


def _analyze_model_sql_in_parallel(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    analysis_cache: AnalysisCacheContext | None,
) -> dict[str, _ModelSqlAnalysis]:
    if not model_inputs:
        return {}
    requests: tuple[_ModelSqlAnalysisRequest, ...] = tuple(
        _model_sql_analysis_request(
            model_input=model_input,
            analysis_cache=analysis_cache,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
        )
        for model_input in model_inputs
    )
    cached_analyses: dict[str, PolyglotAnalysisResult]
    previous_signatures: dict[str, str]
    cached_analyses, previous_signatures = (
        read_model_analyses(
            context=analysis_cache,
            cache_keys=tuple(
                request.cache_key for request in requests if request.cache_key is not None
            ),
            model_names=tuple(_model_name(request.model_input) for request in requests),
            upstream_model_names_by_key={
                request.cache_key: _referenced_model_names(request.model_input)
                for request in requests
                if request.cache_key is not None
            },
        )
        if analysis_cache is not None
        else ({}, {})
    )
    analyses: tuple[_ModelSqlAnalysis, ...] = _analyze_model_sql_requests(
        requests=requests,
        cached_analyses=cached_analyses,
        column_nullability_by_table=column_nullability_by_table,
        column_types_by_table=column_types_by_table,
        inference_profile=inference_profile,
        allow_compact_analysis=allow_compact_analysis,
    )
    current_analyses_by_name: dict[str, PolyglotAnalysisResult] = {
        _model_name(request.model_input): analysis.polyglot_analysis
        for request, analysis in zip(requests, analyses, strict=True)
    }
    current_signatures_by_name: dict[str, str] = {
        model_name: model_analysis_output_signature(analysis)
        for model_name, analysis in current_analyses_by_name.items()
    }
    analyses_to_record_by_name: dict[str, PolyglotAnalysisResult] = {
        _model_name(request.model_input): analysis.polyglot_analysis
        for request, analysis in zip(requests, analyses, strict=True)
        if request.cache_key is None or request.cache_key not in cached_analyses
    }
    changed_signature_names: set[str] = {
        model_name
        for model_name, output_signature in current_signatures_by_name.items()
        if previous_signatures.get(model_name) != output_signature
    }
    analyses_to_record_by_name.update(
        {model_name: current_analyses_by_name[model_name] for model_name in changed_signature_names}
    )
    invalidated_names: set[str] = _downstream_model_names(
        model_inputs=model_inputs,
        changed_names=changed_signature_names,
    )
    if invalidated_names:
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
                    parallel_min_models=_POLYGLOT_PARALLEL_REANALYSIS_MIN_MODELS,
                ),
                strict=True,
            )
        }
        analyses = tuple(
            invalidated_analyses_by_name.get(_model_name(request.model_input), analysis)
            for request, analysis in zip(requests, analyses, strict=True)
        )
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
        current_signatures_by_name = {
            model_name: model_analysis_output_signature(analysis)
            for model_name, analysis in current_analyses_by_name.items()
        }
    if analysis_cache is not None:
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
    parallel_min_models: int = _POLYGLOT_PARALLEL_ANALYSIS_MIN_MODELS,
) -> tuple[_ModelSqlAnalysis, ...]:
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

    if len(requests) < parallel_min_models:
        return tuple(analyze(request) for request in requests)
    workers: int = min(_POLYGLOT_ANALYSIS_WORKERS, len(requests))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return tuple(executor.map(analyze, requests))


def _downstream_model_names(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    changed_names: set[str],
) -> set[str]:
    downstream_by_name: dict[str, set[str]] = {}
    for model_input in model_inputs:
        model_name: str = _model_name(model_input)
        for reference in model_input.references:
            if reference.ref_kind == SqlReferenceKind.REF:
                downstream_by_name.setdefault(reference.ref_name, set()).add(model_name)
    downstream_names: set[str] = set()
    pending: list[str] = list(changed_names)
    while pending:
        for downstream_name in downstream_by_name.get(pending.pop(), set()):
            if downstream_name not in downstream_names and downstream_name not in changed_names:
                downstream_names.add(downstream_name)
                pending.append(downstream_name)
    return downstream_names


def _referenced_model_names(model_input: CompileModelInput) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference.ref_name
                for reference in model_input.references
                if reference.ref_kind == SqlReferenceKind.REF
            }
        )
    )


def _dependency_signatures_by_key(
    *,
    requests: tuple[_ModelSqlAnalysisRequest, ...],
    cached_analyses: dict[str, PolyglotAnalysisResult],
    invalidated_names: set[str],
    current_signatures_by_name: dict[str, str],
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
            for upstream_name in _referenced_model_names(request.model_input)
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
) -> _ModelSqlAnalysis:
    if cached_analysis is not None:
        return _ModelSqlAnalysis(
            polyglot_analysis=cached_analysis,
            placeholders=request.placeholders,
        )
    polyglot_analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
        query_sql=request.query_sql,
        references=request.model_input.references,
        placeholders=request.placeholders,
        column_nullability_by_table=column_nullability_by_table,
        column_types_by_table=column_types_by_table,
        inference_profile=inference_profile,
        allow_compact_analysis=allow_compact_analysis,
    )
    return _ModelSqlAnalysis(
        polyglot_analysis=polyglot_analysis,
        placeholders=request.placeholders,
    )


def _model_sql_analysis_request(
    *,
    model_input: CompileModelInput,
    analysis_cache: AnalysisCacheContext | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
) -> _ModelSqlAnalysisRequest:
    placeholders: dict[str, str] | None = _model_placeholders(model_input)
    query_sql: str = cursor_intrinsics_analysis_sql(
        sql=model_input.query_sql,
        cursor_type=model_input.config.values.get("cursor_type"),
    )
    cache_key: str | None = (
        model_analysis_cache_key(
            context=analysis_cache,
            query_sql=query_sql,
            references=model_input.references,
            placeholders=placeholders,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
        )
        if analysis_cache is not None
        else None
    )
    return _ModelSqlAnalysisRequest(
        model_input=model_input,
        query_sql=query_sql,
        placeholders=placeholders,
        cache_key=cache_key,
    )


def _model_placeholders(model_input: CompileModelInput) -> dict[str, str] | None:
    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    return (
        {str(k): str(v) for k, v in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
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


def _build_column_types_by_table(inputs: CompileProjectInputs) -> dict[str, dict[str, str]]:
    facts: dict[str, dict[str, str]] = {}
    for function_input in inputs.sql_function_inputs:
        if not function_input.return_columns:
            continue
        facts[table_function_analysis_name(function_input.name)] = {
            column.name: column.type for column in function_input.return_columns
        }
    return facts


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
    target: CompiledRelationLocation = _build_seed_relation_target(
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
        ),
        fingerprint_destination=CompiledRelationLocation(
            database=function_input.fingerprint_database,
            schema=function_input.fingerprint_schema,
            name=function_input.name,
            qualified_name=None,
        ),
        language=function_input.language,
        source_file_path=function_input.function_file.file_path,
        runtime_version=function_input.runtime_version,
        entry_point=function_input.entry_point,
        packages=function_input.packages,
        replay_on_change=function_input.replay_on_change,
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
        audit_file=audit_input.audit_file,
        audit_block=audit_input.audit_block,
        sql_body=audit_input.sql_body,
        references=audit_input.references,
        attached_target_kind=normalized_target_kind,
        attached_target_name=audit_input.attached_target_name,
        attached_column_name=audit_input.attached_column_name,
        severity=audit_input.severity,
        run_scope=audit_input.run_scope,
        always_run=audit_input.always_run,
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
        assertion_target_model_names: tuple[str, ...] = _extract_sql_test_assertion_ref_targets(
            assertion_ctes=model_payload.assertion_ctes
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
            expected_model_names=model_payload.expected_model_names,
            assertion_ctes=model_payload.assertion_ctes,
            assertion_names=model_payload.assertion_names,
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
    )


def _macro_sql_test_scope_deps(
    *, tested_macro_names: tuple[str, ...], model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompiledObjectKey, ...]:
    tested_names: frozenset[str] = frozenset(tested_macro_names)
    scope_deps: list[CompiledObjectKey] = []
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_macro_deps: frozenset[str] = frozenset(
            find_macro_call_names(model_input.macro_source_sql)
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


def _extract_sql_test_assertion_ref_targets(
    *, assertion_ctes: tuple[CompileSqlTestCte, ...]
) -> tuple[str, ...]:
    targets: list[str] = []
    cte: CompileSqlTestCte
    for cte in assertion_ctes:
        match: re.Match[str]
        for match in re.finditer(r'__ref\("([^"]+)"\)', cte.sql_body):
            targets.append(match.group(1))
    return tuple(dict.fromkeys(targets))


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
    macro_context: MacroContext = MacroContext(
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
    )


def _resolve_audit_name(audit_input: CompileAuditInput) -> str:
    if audit_input.audit_block.name is not None:
        return audit_input.audit_block.name
    return audit_input.audit_file.file_path.stem


def _resolve_test_name(test_input: CompileSqlTestInput) -> str:
    if test_input.test_block.name is not None:
        return test_input.test_block.name
    return test_input.test_file.file_path.stem


def _build_model_relation_target(
    *, model_input: CompileModelInput, model_name: str
) -> CompiledRelationLocation:
    raw_database: object | None = model_input.config.values.get("database")
    raw_schema: object | None = model_input.config.values.get("schema")
    raw_alias: object | None = model_input.config.values.get("alias")
    database: str | None = raw_database if isinstance(raw_database, str) else None
    schema: str | None = raw_schema if isinstance(raw_schema, str) else None
    name: str = raw_alias if isinstance(raw_alias, str) else model_name
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=name,
        qualified_name=None,
        logical_schema=model_input.config.logical_schema,
        logical_database=model_input.config.logical_database,
    )


def _build_seed_relation_target(
    *,
    seed_entry: SchemaSeedEntry,
    defaults: DefaultsConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> CompiledRelationLocation:
    resolved_namespace: tuple[str | None, str | None] = _resolve_target_namespace(
        defaults=defaults,
        target_config=target_config,
        effective_vars=effective_vars,
    )
    database: str | None = resolved_namespace[0]
    schema: str | None = resolved_namespace[1]
    if seed_entry.database is not None:
        database = _expand_seed_target_value(
            raw_value=seed_entry.database,
            seed_name=seed_entry.name,
            database=database,
            schema=schema,
            effective_vars=effective_vars,
            context_label=f"seed '{seed_entry.name}' database",
        )
    if seed_entry.schema is not None:
        schema = _expand_seed_target_value(
            raw_value=seed_entry.schema,
            seed_name=seed_entry.name,
            database=database,
            schema=schema,
            effective_vars=effective_vars,
            context_label=f"seed '{seed_entry.name}' schema",
        )
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=seed_entry.name,
        qualified_name=None,
    )


def _resolve_target_namespace(
    *,
    defaults: DefaultsConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> tuple[str | None, str | None]:
    database: str | None = defaults.database
    schema: str | None = defaults.schema
    if target_config is not None:
        if target_config.database is not None:
            database = _expand_seed_environment_value(
                raw_value=target_config.database,
                effective_vars=effective_vars,
                context_label="target database",
            )
        if target_config.schema is not None:
            schema = _expand_seed_environment_value(
                raw_value=target_config.schema,
                effective_vars=effective_vars,
                context_label="target schema",
            )
    return database, schema


def _expand_seed_environment_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )


def _expand_seed_target_value(
    *,
    raw_value: str,
    seed_name: str,
    database: str | None,
    schema: str | None,
    effective_vars: dict[str, object],
    context_label: str,
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={
                "model.name": seed_name,
                "model.database": database,
                "model.schema": schema,
                "model.alias": seed_name,
                "destination.database": database,
                "destination.schema": schema,
                "destination.table": seed_name,
                "destination.qualified": _build_seed_destination_qualified_context(
                    database=database,
                    schema=schema,
                    name=seed_name,
                ),
            },
            context_label=context_label,
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    )


def _build_seed_destination_qualified_context(
    *, database: str | None, schema: str | None, name: str
) -> str | None:
    if database is not None and schema is not None:
        return f"{database}.{schema}.{name}"
    if schema is not None:
        return f"{schema}.{name}"
    return None
