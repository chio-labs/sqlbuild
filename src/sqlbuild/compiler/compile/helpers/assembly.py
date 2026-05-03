"""Assemble planner-ready compiled resource objects from compile inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.deps import (
    audit_scope_deps,
    model_build_deps,
    sql_test_scope_deps,
)
from sqlbuild.compiler.compile.helpers.sqlglot_columns import infer_columns_with_sqlglot
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompiledAudit,
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
    CompileSqlTestInput,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType


def assemble_compiled_project(inputs: CompileProjectInputs) -> CompiledProject:
    """Convert attached compile inputs into the planner-ready project view."""

    sqlglot_enabled: bool = inputs.project_config.settings.sqlglot
    seed_names: frozenset[str] = frozenset(
        seed_input.schema_entry.name for seed_input in inputs.seed_inputs
    )
    return CompiledProject(
        run_id=inputs.run_id,
        effective_environment_name=inputs.effective_environment_name,
        effective_connection=inputs.effective_connection,
        effective_vars=inputs.effective_vars,
        models=tuple(
            _assemble_compiled_model(
                model_input, sqlglot_enabled=sqlglot_enabled, seed_names=seed_names
            )
            for model_input in inputs.model_inputs
        ),
        sources=tuple(
            _assemble_compiled_source(source_input) for source_input in inputs.source_inputs
        ),
        seeds=tuple(_assemble_compiled_seed(seed_input) for seed_input in inputs.seed_inputs),
        audits=tuple(_assemble_compiled_audit(audit_input) for audit_input in inputs.audit_inputs),
        sql_tests=tuple(
            _assemble_compiled_sql_test(test_input) for test_input in inputs.test_inputs
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


def _assemble_compiled_seed(seed_input: CompileSeedInput) -> CompiledSeed:
    return CompiledSeed(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SEED, name=seed_input.schema_entry.name
        ),
        deps=(),
        name=seed_input.schema_entry.name,
        seed_file=seed_input.seed_file,
        schema_entry=seed_input.schema_entry,
        schema_file=seed_input.schema_file,
        target=CompiledRelationTarget(
            database=None,
            schema=None,
            name=seed_input.schema_entry.name,
            qualified_name=None,
        ),
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


def _assemble_compiled_sql_test(test_input: CompileSqlTestInput) -> CompiledSqlTest:
    test_name: str = _resolve_test_name(test_input)
    return CompiledSqlTest(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=test_name),
        scope_deps=sql_test_scope_deps(expected_model_names=test_input.expected_model_names),
        name=test_name,
        test_file=test_input.test_file,
        test_block=test_input.test_block,
        sql_body=test_input.sql_body,
        authored_ctes=test_input.authored_ctes,
        mock_model_names=test_input.mock_model_names,
        mock_source_names=test_input.mock_source_names,
        expected_model_names=test_input.expected_model_names,
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
) -> CompiledRelationTarget:
    raw_database: object | None = model_input.config.values.get("database")
    raw_schema: object | None = model_input.config.values.get("schema")
    raw_alias: object | None = model_input.config.values.get("alias")
    database: str | None = raw_database if isinstance(raw_database, str) else None
    schema: str | None = raw_schema if isinstance(raw_schema, str) else None
    name: str = raw_alias if isinstance(raw_alias, str) else model_name
    qualified_name: str | None = None
    if database is not None and schema is not None:
        qualified_name = f"{database}.{schema}.{name}"
    elif schema is not None:
        qualified_name = f"{schema}.{name}"
    return CompiledRelationTarget(
        database=database,
        schema=schema,
        name=name,
        qualified_name=qualified_name,
        logical_schema=model_input.config.logical_schema,
        logical_database=model_input.config.logical_database,
    )
