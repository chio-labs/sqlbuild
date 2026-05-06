"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.deps import (
    audit_scope_deps,
    function_build_deps,
    model_build_deps,
    sql_test_scope_deps,
)
from sqlbuild.compiler.compile.helpers.macros import expand_sql_macros
from sqlbuild.compiler.compile.helpers.sqlglot_columns import infer_columns_with_sqlglot
from sqlbuild.compiler.compile.helpers.templating import expand_template_data
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompiledSqlTest,
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlTestInput,
    InferredColumn,
    MacroContext,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.spec.models.project import (
    DefaultsConfig,
    EnvironmentConfig,
    resolve_effective_adapter_name,
)
from sqlbuild.spec.models.schema import SchemaSeedEntry


def assemble_compiled_project(inputs: CompileProjectInputs) -> CompiledProject:
    """Convert attached compile inputs into the planner-ready project view."""

    sqlglot_enabled: bool = inputs.effective_settings.sqlglot
    seed_names: frozenset[str] = frozenset(
        seed_input.schema_entry.name for seed_input in inputs.seed_inputs
    )
    return CompiledProject(
        run_id=inputs.run_id,
        effective_environment_name=inputs.effective_environment_name,
        effective_connection=inputs.effective_connection,
        effective_vars=inputs.effective_vars,
        settings=inputs.effective_settings,
        models=tuple(
            _assemble_compiled_model(
                model_input, sqlglot_enabled=sqlglot_enabled, seed_names=seed_names
            )
            for model_input in inputs.model_inputs
        ),
        sources=tuple(
            _assemble_compiled_source(source_input) for source_input in inputs.source_inputs
        ),
        seeds=tuple(
            _assemble_compiled_seed(
                seed_input,
                defaults=inputs.project_config.defaults,
                environment_config=inputs.effective_environment,
                effective_vars=inputs.effective_vars,
            )
            for seed_input in inputs.seed_inputs
        ),
        functions=tuple(
            _assemble_compiled_function(function_input, seed_names=seed_names)
            for function_input in inputs.sql_function_inputs
        ),
        audits=tuple(_assemble_compiled_audit(audit_input) for audit_input in inputs.audit_inputs),
        sql_tests=tuple(
            _assemble_compiled_sql_test(test_input, model_inputs=inputs.model_inputs, inputs=inputs)
            for test_input in inputs.test_inputs
        ),
    )


def _assemble_compiled_model(
    model_input: CompileModelInput,
    *,
    sqlglot_enabled: bool,
    seed_names: frozenset[str] = frozenset(),
) -> CompiledModel:
    model_name: str = model_input.model_file.file_path.stem
    inferred_columns: tuple[InferredColumn, ...] | None = None
    raw_placeholders: object | None = model_input.config.values.get("placeholders")
    placeholders: dict[str, str] | None = (
        {str(k): str(v) for k, v in raw_placeholders.items()}
        if isinstance(raw_placeholders, dict)
        else None
    )
    if sqlglot_enabled:
        inferred_columns = infer_columns_with_sqlglot(
            query_sql=model_input.query_sql, placeholders=placeholders
        )
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=model_name),
        deps=model_build_deps(references=model_input.references, seed_names=seed_names),
        name=model_name,
        relative_path=model_input.model_file.relative_path,
        query_sql=model_input.query_sql,
        config=model_input.config,
        target=_build_model_relation_target(model_input=model_input, model_name=model_name),
        references=model_input.references,
        schema_entry=model_input.schema_entry,
        inferred_columns=inferred_columns,
        authored_sql=model_input.model_file.contents,
        output_column_locations=model_input.model_file.output_column_locations,
    )


def _assemble_compiled_source(source_input: CompileSourceInput) -> CompiledSource:
    return CompiledSource(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE, name=source_input.source_entry.name
        ),
        deps=(),
        name=source_input.source_entry.name,
        source_entry=source_input.source_entry,
        source_file=source_input.source_file,
    )


def _assemble_compiled_seed(
    seed_input: CompileSeedInput,
    *,
    defaults: DefaultsConfig,
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> CompiledSeed:
    target: CompiledRelationTarget = _build_seed_relation_target(
        seed_entry=seed_input.schema_entry,
        defaults=defaults,
        environment_config=environment_config,
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
        target=target,
    )


def _assemble_compiled_function(
    function_input: CompileSqlFunctionInput,
    *,
    seed_names: frozenset[str] = frozenset(),
) -> CompiledFunction:
    return CompiledFunction(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.FUNCTION,
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
        target=CompiledRelationTarget(
            database=function_input.database,
            schema=function_input.schema,
            name=function_input.name,
            qualified_name=None,
        ),
        fingerprint_target=CompiledRelationTarget(
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
        query_change_backfill=function_input.query_change_backfill,
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
    )


def _assemble_compiled_sql_test(
    test_input: CompileSqlTestInput,
    *,
    model_inputs: tuple[CompileModelInput, ...],
    inputs: CompileProjectInputs,
) -> CompiledSqlTest:
    test_name: str = _resolve_test_name(test_input)
    return CompiledSqlTest(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=test_name),
        scope_deps=sql_test_scope_deps(expected_model_names=test_input.expected_model_names),
        name=test_name,
        test_file=test_input.test_file,
        test_block=test_input.test_block,
        sql_body=test_input.sql_body,
        authored_ctes=test_input.authored_ctes,
        macro_mocks=test_input.macro_mocks,
        model_query_overrides=_build_test_model_query_overrides(
            test_input=test_input,
            model_inputs=model_inputs,
            inputs=inputs,
        ),
        mock_model_names=test_input.mock_model_names,
        mock_source_names=test_input.mock_source_names,
        mock_seed_names=test_input.mock_seed_names,
        expected_model_names=test_input.expected_model_names,
    )


def _build_test_model_query_overrides(
    *,
    test_input: CompileSqlTestInput,
    model_inputs: tuple[CompileModelInput, ...],
    inputs: CompileProjectInputs,
) -> dict[str, str]:
    """Build per-test model SQL with macro mocks applied."""

    if not test_input.macro_mocks:
        return {}
    macro_context: MacroContext = MacroContext(
        adapter_name=resolve_effective_adapter_name(
            project_config=inputs.project_config,
            local_config=inputs.local_config,
        ),
        sqlglot_enabled=inputs.effective_settings.sqlglot,
        environment_name=inputs.effective_environment_name,
        vars=inputs.effective_vars,
    )
    overrides: dict[str, str] = {}
    model_input: CompileModelInput
    for model_input in model_inputs:
        model_name: str = model_input.model_file.file_path.stem
        macro_source_sql: str = model_input.macro_source_sql or model_input.query_sql
        overrides[model_name] = expand_sql_macros(
            sql=macro_source_sql,
            file_path=model_input.model_file.file_path,
            loaded_macros=inputs.loaded_macros,
            macro_overrides=test_input.macro_mocks,
            macro_context=macro_context,
        )
    return overrides


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
) -> CompiledRelationTarget:
    raw_database: object | None = model_input.config.values.get("database")
    raw_schema: object | None = model_input.config.values.get("schema")
    raw_alias: object | None = model_input.config.values.get("alias")
    database: str | None = raw_database if isinstance(raw_database, str) else None
    schema: str | None = raw_schema if isinstance(raw_schema, str) else None
    name: str = raw_alias if isinstance(raw_alias, str) else model_name
    return CompiledRelationTarget(
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
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> CompiledRelationTarget:
    resolved_namespace: tuple[str | None, str | None] = _resolve_target_namespace(
        defaults=defaults,
        environment_config=environment_config,
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
    return CompiledRelationTarget(
        database=database,
        schema=schema,
        name=seed_entry.name,
        qualified_name=None,
    )


def _resolve_target_namespace(
    *,
    defaults: DefaultsConfig,
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> tuple[str | None, str | None]:
    database: str | None = defaults.database
    schema: str | None = defaults.schema
    if environment_config is not None:
        if environment_config.database is not None:
            database = _expand_seed_environment_value(
                raw_value=environment_config.database,
                effective_vars=effective_vars,
                context_label="environment database",
            )
        if environment_config.schema is not None:
            schema = _expand_seed_environment_value(
                raw_value=environment_config.schema,
                effective_vars=effective_vars,
                context_label="environment schema",
            )
    return database, schema


def _expand_seed_environment_value(
    *, raw_value: str, effective_vars: dict[str, str], context_label: str
) -> str | None:
    if raw_value == "preserve":
        return None
    return str(
        expand_template_data(
            raw_value,
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
    effective_vars: dict[str, str],
    context_label: str,
) -> str | None:
    if raw_value == "preserve":
        return None
    return str(
        expand_template_data(
            raw_value,
            variables=effective_vars,
            context_values={
                "model.name": seed_name,
                "model.database": database,
                "model.schema": schema,
                "model.alias": seed_name,
                "target.database": database,
                "target.schema": schema,
                "target.table": seed_name,
                "target.qualified": _build_seed_target_qualified_context(
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


def _build_seed_target_qualified_context(
    *, database: str | None, schema: str | None, name: str
) -> str | None:
    if database is not None and schema is not None:
        return f"{database}.{schema}.{name}"
    if schema is not None:
        return f"{schema}.{name}"
    return None
