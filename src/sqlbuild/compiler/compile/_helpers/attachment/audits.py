"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.auditing.constants import (
    MEASUREMENT_MINIMUM_SAMPLES_HEADER_KEY,
    MEASUREMENT_THRESHOLDS_HEADER_KEY,
)
from sqlbuild.compiler.auditing.main._builtins import build_builtin_audit_resolution
from sqlbuild.compiler.auditing.main._parse_audit_instance import (
    parse_measurement_thresholds,
    parse_minimum_samples,
)
from sqlbuild.compiler.auditing.models import MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, AuditSeverity
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    validate_audit_references,
)
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    merge_call_site_references,
)
from sqlbuild.compiler.compile._helpers.named_declarations.core import (
    declaration_file_expansion,
    named_declaration_usages,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.arguments import (
    render_parameterized_sql,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql_result,
)
from sqlbuild.compiler.compile.constants import SINGULAR_AUDIT_NOT_CROSS_RESOURCE_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileAuditInput,
    CompileModelInput,
    CompilerDiagnostic,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    LoadedMacro,
    MacroContext,
    ModelInputBuildContext,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SchemaColumn,
    SettingsConfig,
    SourceColumnEntry,
)

_CROSS_MODEL_MINIMUM: int = 2


@dataclass(frozen=True)
class _AuditConsumer:
    """The resource that attaches a generic audit, used for scope visibility and placement."""

    identity: ResourceIdentity
    path: Path


@dataclass(frozen=True)
class _AuditAttachmentContext:
    """Run-constant inputs shared across attached audit rendering."""

    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    loaded_macros: dict[str, LoadedMacro]
    known_model_names: set[str]
    known_seed_names: set[str]
    known_source_names: set[str]
    default_audit_severity: AuditSeverity | None
    default_audit_run_scope: str | None
    effective_vars: dict[str, object]
    macro_context: MacroContext
    declaration_expansion: DeclarationExpansionContext
    sql_lexical_syntax: SqlLexicalSyntax
    scoped_declarations: dict[tuple[Path, DeclarationIdentity], DeclarationExpansionContext] = (
        field(default_factory=dict, compare=False, repr=False)
    )

    def remember_scoped_declarations(
        self,
        *,
        key: tuple[Path, DeclarationIdentity],
        declarations: DeclarationExpansionContext,
    ) -> None:
        """Retain one resolved audit scope for reuse in this compile invocation."""

        self.scoped_declarations[key] = declarations


def build_project_audit_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    model_inputs: tuple[CompileModelInput, ...],
    source_inputs: tuple[CompileSourceInput, ...],
    seed_inputs: tuple[CompileSeedInput, ...],
) -> tuple[tuple[CompileAuditInput, ...], tuple[CompilerDiagnostic, ...]]:
    """Resolve built-in-aware generic audits and build every project audit input."""

    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    diagnostics: tuple[CompilerDiagnostic, ...]
    generic_audit_definitions, diagnostics = build_builtin_audit_resolution(
        index_generic_audit_definitions(discovered_inputs.audit_files)
    )
    audit_inputs: tuple[CompileAuditInput, ...] = build_audit_inputs(
        discovered_inputs=discovered_inputs,
        context=context,
        model_inputs=model_inputs,
        source_inputs=source_inputs,
        generic_audit_definitions=generic_audit_definitions,
        seed_inputs=seed_inputs,
    )
    return audit_inputs, diagnostics


def build_audit_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    model_inputs: tuple[CompileModelInput, ...],
    source_inputs: tuple[CompileSourceInput, ...],
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    | None = None,
    seed_inputs: tuple[CompileSeedInput, ...] = (),
) -> tuple[CompileAuditInput, ...]:
    """Build compile-time audit inputs from discovered SQL audit blocks."""

    effective_settings: SettingsConfig = context.effective_settings
    effective_vars: dict[str, object] = context.effective_vars
    macro_context: MacroContext = context.macro_context
    loaded_macros: dict[str, LoadedMacro] = context.loaded_macros
    declaration_expansion: DeclarationExpansionContext = context.declaration_expansion
    sql_lexical_syntax: SqlLexicalSyntax = context.sql_lexical_syntax
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    if generic_audit_definitions is None:
        generic_audit_definitions = index_generic_audit_definitions(discovered_inputs.audit_files)
    default_audit_severity: AuditSeverity | None = effective_settings.default_audit_severity
    default_audit_run_scope: str | None = effective_settings.default_audit_run_scope
    attachment_context: _AuditAttachmentContext = _AuditAttachmentContext(
        generic_audit_definitions=generic_audit_definitions,
        loaded_macros=loaded_macros,
        known_model_names=known_model_names,
        known_seed_names=known_seed_names,
        known_source_names=known_source_names,
        default_audit_severity=default_audit_severity,
        default_audit_run_scope=default_audit_run_scope,
        effective_vars=effective_vars,
        macro_context=macro_context,
        declaration_expansion=declaration_expansion,
        sql_lexical_syntax=sql_lexical_syntax,
    )
    audit_inputs: list[CompileAuditInput] = []
    audit_file: DiscoveredAuditFile
    for audit_file in discovered_inputs.audit_files:
        if is_generic_audit_file(audit_file):
            continue
        audit_block: DiscoveredAuditBlock
        for audit_block in audit_file.blocks:
            audit_identity: DeclarationIdentity = DeclarationIdentity(
                DeclarationKind.SINGULAR_AUDIT,
                audit_block.name or audit_file.relative_path.stem,
            )
            scoped_declarations: DeclarationExpansionContext = _scoped_audit_declarations(
                context=attachment_context,
                file_path=audit_file.file_path,
                consumer=audit_identity,
            )
            expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
                sql=audit_block.sql_body,
                file_path=audit_file.file_path,
                effective_vars=effective_vars,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                declarations=scoped_declarations.declarations,
                declaration_resolver=scoped_declarations.resolver,
                value_renderer=scoped_declarations.value_renderer,
                collection_rendering=scoped_declarations.collection_rendering,
            )
            expanded_sql_body: str = expansion.sql
            evidence_expansion: AuthoredSqlExpansionResult | None = None
            expanded_evidence_sql: str | None = None
            if audit_block.evidence_sql is not None:
                evidence_expansion = expand_authored_sql_result(
                    sql=audit_block.evidence_sql,
                    file_path=audit_file.file_path,
                    effective_vars=effective_vars,
                    loaded_macros=loaded_macros,
                    macro_context=macro_context,
                    declarations=scoped_declarations.declarations,
                    declaration_resolver=scoped_declarations.resolver,
                    value_renderer=scoped_declarations.value_renderer,
                    collection_rendering=scoped_declarations.collection_rendering,
                )
                expanded_evidence_sql = evidence_expansion.sql
            reject_cursor_intrinsics(
                sql=expanded_sql_body,
                context=f"Audit '{audit_block.name or audit_file.file_path.stem}'",
            )
            if expanded_evidence_sql is not None:
                reject_cursor_intrinsics(
                    sql=expanded_evidence_sql,
                    context=f"Audit '{audit_block.name or audit_file.file_path.stem}' evidence",
                )
            references: tuple[CompileSqlReference, ...] = merge_call_site_references(
                references=_combined_references(
                    expanded_sql_body, expanded_evidence_sql, syntax=sql_lexical_syntax
                ),
                argument_references=_argument_references(expansion, evidence_expansion),
            )
            validate_audit_references(
                references=references,
                audit_file=audit_file,
                known_model_names=known_model_names,
                known_seed_names=known_seed_names,
                known_source_names=known_source_names,
            )
            referenced_resources: tuple[ResourceIdentity, ...] = singular_audit_resources(
                references=references,
                audit_file=audit_file,
                audit_name=audit_identity.name,
            )
            header_severity: str | None = _str_from_dict(
                values=audit_block.header_values, key="severity"
            )
            header_run_scope: str | None = _str_from_dict(
                values=audit_block.header_values, key="run_scope"
            )
            header_always_run: bool = _bool_from_dict(
                values=audit_block.header_values, key="always_run"
            )
            thresholds: MeasurementThresholds | None = parse_measurement_thresholds(
                raw_value=audit_block.header_values.get("thresholds"),
                file_path=audit_file.relative_path,
                label="standalone measurement audit",
                error_class=CompileInputError,
            )
            minimum_samples: int | None = parse_minimum_samples(
                raw_value=audit_block.header_values.get("minimum_samples"),
                file_path=audit_file.relative_path,
                label="standalone measurement audit",
                error_class=CompileInputError,
            )
            if audit_block.evaluation_mode == AuditEvaluationMode.MEASUREMENT:
                if header_severity is not None:
                    raise CompileInputError(
                        f"{audit_file.relative_path}: measurement audits must not define severity; "
                        "severity derives from thresholds"
                    )
                if thresholds is None:
                    raise CompileInputError(
                        f"{audit_file.relative_path}: standalone measurement audit must define "
                        "thresholds in its AUDIT header"
                    )
                resolved_severity: AuditSeverity = measurement_policy_severity(thresholds)
            else:
                resolved_severity = resolve_audit_severity(
                    instance_severity=header_severity,
                    default_severity=default_audit_severity,
                    audit_label=str(audit_file.relative_path),
                )
            resolved_run_scope: str = resolve_audit_run_scope(
                instance_run_scope=header_run_scope,
                default_run_scope=default_audit_run_scope,
            )
            audit_inputs.append(
                CompileAuditInput(
                    audit_file=audit_file,
                    audit_block=audit_block,
                    sql_body=expanded_sql_body,
                    evaluation_mode=audit_block.evaluation_mode,
                    measurement_contract=audit_block.measurement_contract,
                    thresholds=thresholds,
                    minimum_samples=minimum_samples,
                    measure_sql=(
                        expanded_sql_body
                        if audit_block.evaluation_mode == AuditEvaluationMode.MEASUREMENT
                        else None
                    ),
                    evidence_sql=expanded_evidence_sql,
                    references=references,
                    severity=resolved_severity,
                    run_scope=resolved_run_scope,
                    always_run=header_always_run,
                    declaration_usages=(
                        expansion.usages
                        + (() if evidence_expansion is None else evidence_expansion.usages)
                        + tuple(
                            UsageRecord(consumer=resource, declaration=audit_identity)
                            for resource in referenced_resources
                        )
                    ),
                )
            )
    model_input: CompileModelInput
    for model_input in model_inputs:
        if model_input.schema_entry is None:
            continue
        audit_inputs.extend(
            build_model_attached_audit_inputs(
                model_input=model_input,
                context=attachment_context,
            )
        )
    source_input: CompileSourceInput
    for source_input in source_inputs:
        audit_inputs.extend(
            build_source_attached_audit_inputs(
                source_input=source_input,
                context=attachment_context,
            )
        )
    seed_input: CompileSeedInput
    for seed_input in seed_inputs:
        audit_inputs.extend(
            build_seed_attached_audit_inputs(seed_input=seed_input, context=attachment_context)
        )
    return tuple(audit_inputs)


def build_model_attached_audit_inputs(
    *,
    model_input: CompileModelInput,
    context: _AuditAttachmentContext,
) -> tuple[CompileAuditInput, ...]:
    """Render schema-attached model audits into compile audit inputs."""

    if model_input.schema_entry is None:
        raise CompileInputError(
            f"Model file {model_input.model_file.relative_path} has no schema entry for "
            "schema-attached audits"
        )
    owner_file: Path = (
        model_input.schema_file.relative_path
        if model_input.schema_file is not None
        else model_input.model_file.relative_path
    )
    model_consumer: _AuditConsumer = _AuditConsumer(
        identity=ResourceIdentity(ResourceKind.MODEL, model_input.model_file.file_path.stem),
        path=model_input.model_file.relative_path,
    )
    attached_audit_inputs: list[CompileAuditInput] = []
    audit_instance: SchemaAuditInstance
    for audit_instance in model_input.schema_entry.audits:
        attached_column_name: str | None = _explicit_audit_column_name(
            audit_instance=audit_instance,
        )
        attached_audit_inputs.append(
            build_attached_audit_input(
                audit_instance=audit_instance,
                owner_file=owner_file,
                implicit_arguments={
                    "model": model_input.model_file.file_path.stem,
                    "relation": SqlReferenceKind.REF.example_call(
                        model_input.model_file.file_path.stem,
                        quote='"',
                    ),
                },
                attached_target_kind=AttachedAuditTargetKind.MODEL,
                attached_target_name=model_input.model_file.file_path.stem,
                attached_column_name=attached_column_name,
                context=context,
                consumer=model_consumer,
            )
        )
    column_entry: SchemaColumn
    for column_entry in model_input.schema_entry.columns:
        column_owner_file: Path = (
            column_entry.location.path if column_entry.location is not None else owner_file
        )
        for audit_instance in column_entry.audits:
            audit_owner_file: Path = (
                audit_instance.location.path
                if audit_instance.location is not None
                else column_owner_file
            )
            attached_audit_inputs.append(
                build_attached_audit_input(
                    audit_instance=audit_instance,
                    owner_file=audit_owner_file,
                    implicit_arguments={
                        "model": model_input.model_file.file_path.stem,
                        "relation": SqlReferenceKind.REF.example_call(
                            model_input.model_file.file_path.stem,
                            quote='"',
                        ),
                        "column": column_entry.name,
                    },
                    attached_target_kind=AttachedAuditTargetKind.MODEL,
                    attached_target_name=model_input.model_file.file_path.stem,
                    attached_column_name=column_entry.name,
                    context=context,
                    consumer=model_consumer,
                )
            )
    return tuple(attached_audit_inputs)


def build_source_attached_audit_inputs(
    *,
    source_input: CompileSourceInput,
    context: _AuditAttachmentContext,
) -> tuple[CompileAuditInput, ...]:
    """Render source-attached audits into compile audit inputs."""

    source_consumer: _AuditConsumer = _AuditConsumer(
        identity=ResourceIdentity(ResourceKind.SOURCE, source_input.source_entry.name),
        path=source_input.source_file.relative_path,
    )
    attached_audit_inputs: list[CompileAuditInput] = []
    audit_instance: SchemaAuditInstance
    for audit_instance in source_input.source_entry.audits:
        attached_audit_inputs.append(
            build_attached_audit_input(
                audit_instance=audit_instance,
                owner_file=source_input.source_file.relative_path,
                implicit_arguments={
                    "source": source_input.source_entry.name,
                    "relation": SqlReferenceKind.SOURCE.example_call(
                        source_input.source_entry.name,
                        quote='"',
                    ),
                },
                attached_target_kind=AttachedAuditTargetKind.SOURCE,
                attached_target_name=source_input.source_entry.name,
                attached_column_name=None,
                context=context,
                consumer=source_consumer,
            )
        )
    column_entry: SourceColumnEntry
    for column_entry in source_input.source_entry.columns:
        for audit_instance in column_entry.audits:
            attached_audit_inputs.append(
                build_attached_audit_input(
                    audit_instance=audit_instance,
                    owner_file=source_input.source_file.relative_path,
                    implicit_arguments={
                        "source": source_input.source_entry.name,
                        "relation": SqlReferenceKind.SOURCE.example_call(
                            source_input.source_entry.name,
                            quote='"',
                        ),
                        "column": column_entry.name,
                    },
                    attached_target_kind=AttachedAuditTargetKind.SOURCE,
                    attached_target_name=source_input.source_entry.name,
                    attached_column_name=column_entry.name,
                    context=context,
                    consumer=source_consumer,
                )
            )
    return tuple(attached_audit_inputs)


def build_seed_attached_audit_inputs(
    *,
    seed_input: CompileSeedInput,
    context: _AuditAttachmentContext,
) -> tuple[CompileAuditInput, ...]:
    """Render seed-attached table and column audits into compile audit inputs."""

    seed_name: str = seed_input.schema_entry.name
    seed_consumer: _AuditConsumer = _AuditConsumer(
        identity=ResourceIdentity(ResourceKind.SEED, seed_name),
        path=seed_input.seed_file.relative_path,
    )
    implicit_arguments: dict[str, object] = {
        "seed": seed_name,
        "relation": SqlReferenceKind.SEED.example_call(seed_name, quote='"'),
    }
    attached_audit_inputs: list[CompileAuditInput] = [
        build_attached_audit_input(
            audit_instance=audit_instance,
            owner_file=seed_input.schema_file.relative_path,
            implicit_arguments=implicit_arguments,
            attached_target_kind=AttachedAuditTargetKind.SEED,
            attached_target_name=seed_name,
            attached_column_name=_explicit_audit_column_name(audit_instance=audit_instance),
            context=context,
            consumer=seed_consumer,
        )
        for audit_instance in seed_input.schema_entry.audits
    ]
    column_entry: SchemaColumn
    for column_entry in seed_input.schema_entry.columns:
        attached_audit_inputs.extend(
            build_attached_audit_input(
                audit_instance=audit_instance,
                owner_file=seed_input.schema_file.relative_path,
                implicit_arguments={**implicit_arguments, "column": column_entry.name},
                attached_target_kind=AttachedAuditTargetKind.SEED,
                attached_target_name=seed_name,
                attached_column_name=column_entry.name,
                context=context,
                consumer=seed_consumer,
            )
            for audit_instance in column_entry.audits
        )
    return tuple(attached_audit_inputs)


def _explicit_audit_column_name(
    *,
    audit_instance: SchemaAuditInstance,
) -> str | None:
    raw_column: object | None = audit_instance.arguments.get("column")
    return raw_column if isinstance(raw_column, str) else None


def _scoped_audit_declarations(
    *, context: _AuditAttachmentContext, file_path: Path, consumer: DeclarationIdentity
) -> DeclarationExpansionContext:
    key: tuple[Path, DeclarationIdentity] = (file_path, consumer)
    cached: DeclarationExpansionContext | None = context.scoped_declarations.get(key)
    if cached is not None:
        return cached
    resolved: DeclarationExpansionContext = declaration_file_expansion(
        context=context.declaration_expansion,
        file_path=file_path,
        consumer=consumer,
    )
    context.remember_scoped_declarations(key=key, declarations=resolved)
    return resolved


def build_attached_audit_input(
    *,
    audit_instance: SchemaAuditInstance,
    owner_file: Path,
    implicit_arguments: dict[str, object],
    attached_target_kind: str,
    attached_target_name: str,
    attached_column_name: str | None,
    context: _AuditAttachmentContext,
    consumer: _AuditConsumer,
) -> CompileAuditInput:
    """Render one attached generic audit instance into a compile audit input."""

    definition: tuple[DiscoveredAuditFile, DiscoveredAuditBlock] | None = (
        context.generic_audit_definitions.get(audit_instance.definition_name)
    )
    if definition is None:
        raise CompileInputError(
            f"{owner_file} references unknown generic audit '{audit_instance.definition_name}'"
        )
    attachment_usages: tuple[UsageRecord, ...] = named_declaration_usages(
        resolver=context.declaration_expansion.resolver,
        kind=DeclarationKind.AUDIT,
        name=audit_instance.definition_name,
        consumer=consumer.identity,
        consumer_path=consumer.path,
    )
    evaluation_mode: AuditEvaluationMode = definition[1].evaluation_mode
    if evaluation_mode == AuditEvaluationMode.MEASUREMENT:
        if audit_instance.severity is not None:
            raise CompileInputError(
                f"{owner_file} audit '{audit_instance.definition_name}': measurement audit "
                "attachments must not define severity; severity derives from thresholds"
            )
        if audit_instance.thresholds is None:
            raise CompileInputError(
                f"{owner_file} audit '{audit_instance.definition_name}': measurement audit "
                "attachments must define at least one threshold"
            )
    elif audit_instance.thresholds is not None or audit_instance.minimum_samples is not None:
        raise CompileInputError(
            f"{owner_file} audit '{audit_instance.definition_name}': thresholds and "
            "minimum_samples are only valid for measurement audits"
        )
    merged_arguments: dict[str, object] = merge_audit_arguments(
        owner_file=owner_file,
        definition_name=audit_instance.definition_name,
        implicit_arguments=implicit_arguments,
        explicit_arguments=audit_instance.arguments,
    )
    rendered_sql_body: str = render_generic_audit_sql(
        sql=definition[1].sql_body,
        arguments=merged_arguments,
        owner_file=owner_file,
        definition_name=audit_instance.definition_name,
    )
    rendered_evidence_sql: str | None = None
    if definition[1].evidence_sql is not None:
        rendered_evidence_sql = render_generic_audit_sql(
            sql=definition[1].evidence_sql,
            arguments=merged_arguments,
            owner_file=owner_file,
            definition_name=audit_instance.definition_name,
        )
    scoped_declarations: DeclarationExpansionContext = _scoped_audit_declarations(
        context=context,
        file_path=definition[0].file_path,
        consumer=DeclarationIdentity(DeclarationKind.AUDIT, audit_instance.definition_name),
    )
    expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
        sql=rendered_sql_body,
        file_path=definition[0].file_path,
        effective_vars=context.effective_vars,
        loaded_macros=context.loaded_macros,
        macro_context=context.macro_context,
        declarations=scoped_declarations.declarations,
        declaration_resolver=scoped_declarations.resolver,
        value_renderer=scoped_declarations.value_renderer,
        collection_rendering=scoped_declarations.collection_rendering,
    )
    expanded_sql_body: str = expansion.sql
    evidence_expansion: AuthoredSqlExpansionResult | None = None
    expanded_evidence_sql: str | None = None
    if rendered_evidence_sql is not None:
        evidence_expansion = expand_authored_sql_result(
            sql=rendered_evidence_sql,
            file_path=definition[0].file_path,
            effective_vars=context.effective_vars,
            loaded_macros=context.loaded_macros,
            macro_context=context.macro_context,
            declarations=scoped_declarations.declarations,
            declaration_resolver=scoped_declarations.resolver,
            value_renderer=scoped_declarations.value_renderer,
            collection_rendering=scoped_declarations.collection_rendering,
        )
        expanded_evidence_sql = evidence_expansion.sql
    reject_cursor_intrinsics(
        sql=expanded_sql_body,
        context=f"Audit '{audit_instance.definition_name}'",
    )
    if expanded_evidence_sql is not None:
        reject_cursor_intrinsics(
            sql=expanded_evidence_sql,
            context=f"Audit '{audit_instance.definition_name}' evidence",
        )
    references: tuple[CompileSqlReference, ...] = merge_call_site_references(
        references=_combined_references(
            expanded_sql_body, expanded_evidence_sql, syntax=context.sql_lexical_syntax
        ),
        argument_references=_argument_references(expansion, evidence_expansion),
    )
    validate_audit_references(
        references=references,
        audit_file=definition[0],
        known_model_names=context.known_model_names,
        known_seed_names=context.known_seed_names,
        known_source_names=context.known_source_names,
    )
    audit_label: str = f"{owner_file} audit '{audit_instance.definition_name}'"
    resolved_severity: AuditSeverity = (
        measurement_policy_severity(audit_instance.thresholds)
        if audit_instance.thresholds is not None
        else resolve_audit_severity(
            instance_severity=audit_instance.severity,
            default_severity=context.default_audit_severity,
            audit_label=audit_label,
        )
    )
    resolved_run_scope: str = resolve_audit_run_scope(
        instance_run_scope=audit_instance.run_scope,
        default_run_scope=context.default_audit_run_scope,
    )
    validate_model_attached_audit_references(
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        audit_label=audit_label,
    )
    return CompileAuditInput(
        audit_file=definition[0],
        audit_block=definition[1],
        sql_body=expanded_sql_body,
        evaluation_mode=evaluation_mode,
        measurement_contract=definition[1].measurement_contract,
        thresholds=audit_instance.thresholds,
        minimum_samples=audit_instance.minimum_samples,
        measure_sql=(
            expanded_sql_body if evaluation_mode == AuditEvaluationMode.MEASUREMENT else None
        ),
        evidence_sql=expanded_evidence_sql,
        evidence_limit=audit_instance.evidence_limit,
        name=audit_instance.name,
        description=audit_instance.description,
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        attached_column_name=attached_column_name,
        severity=resolved_severity,
        run_scope=resolved_run_scope,
        always_run=audit_instance.always_run,
        declaration_usages=(
            attachment_usages
            + expansion.usages
            + (() if evidence_expansion is None else evidence_expansion.usages)
        ),
    )


def index_generic_audit_definitions(
    audit_files: tuple[DiscoveredAuditFile, ...],
) -> dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]:
    """Index project-wide and scoped generic audit definitions by name."""

    definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = {}
    audit_file: DiscoveredAuditFile
    for audit_file in audit_files:
        if not is_generic_audit_file(audit_file):
            continue
        if len(audit_file.blocks) != 1:
            raise CompileInputError(
                f"Generic audit definition {audit_file.relative_path} must contain exactly "
                "one AUDIT block"
            )
        block: DiscoveredAuditBlock = audit_file.blocks[0]
        if block.evaluation_mode == AuditEvaluationMode.MEASUREMENT and (
            MEASUREMENT_THRESHOLDS_HEADER_KEY in block.header_values
            or MEASUREMENT_MINIMUM_SAMPLES_HEADER_KEY in block.header_values
        ):
            raise CompileInputError(
                f"Generic measurement audit definition {audit_file.relative_path} must not "
                "define thresholds or minimum_samples in its AUDIT header; attachment owns policy"
            )
        definition_name: str = audit_file.file_path.stem
        if definition_name in definitions:
            raise CompileInputError(
                f"Duplicate generic audit definition found for '{definition_name}' in "
                f"{definitions[definition_name][0].relative_path} and {audit_file.relative_path}"
            )
        definitions[definition_name] = (audit_file, audit_file.blocks[0])
    return definitions


def is_generic_audit_file(audit_file: DiscoveredAuditFile) -> bool:
    """Return whether a discovered audit file is a generic definition."""

    return audit_file.declaration_kind is DeclarationKind.AUDIT


def singular_audit_resources(
    *,
    references: tuple[CompileSqlReference, ...],
    audit_file: DiscoveredAuditFile,
    audit_name: str,
) -> tuple[ResourceIdentity, ...]:
    """Return the resources a singular audit references, reporting P004 if not cross-resource."""

    model_names: frozenset[str] = frozenset(
        reference.ref_name for reference in references if reference.ref_kind == SqlReferenceKind.REF
    )
    companion_kinds: dict[SqlReferenceKind, ResourceKind] = {
        SqlReferenceKind.SOURCE: ResourceKind.SOURCE,
        SqlReferenceKind.SEED: ResourceKind.SEED,
        SqlReferenceKind.TABLE_FUNCTION: ResourceKind.FUNCTION,
    }
    companions: frozenset[ResourceIdentity] = frozenset(
        ResourceIdentity(companion_kinds[SqlReferenceKind(reference.ref_kind)], reference.ref_name)
        for reference in references
        if reference.ref_kind in companion_kinds
    )
    resources: tuple[ResourceIdentity, ...] = tuple(
        sorted({*(ResourceIdentity(ResourceKind.MODEL, name) for name in model_names), *companions})
    )
    if len(model_names) < _CROSS_MODEL_MINIMUM and not (model_names and companions):
        message, help_text = _single_resource_problem(
            model_names=model_names, companions=companions
        )
        report_compile_diagnostic(
            key=(
                SINGULAR_AUDIT_NOT_CROSS_RESOURCE_CODE,
                audit_file.relative_path.as_posix(),
                audit_name,
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=SINGULAR_AUDIT_NOT_CROSS_RESOURCE_CODE,
                message=f"Singular audit '{audit_name}' in {audit_file.relative_path} {message}",
                resource_type=CompiledResourceType.AUDIT,
                resource_name=audit_name,
                path=audit_file.relative_path,
                help=help_text,
            ),
        )
    return resources


def _single_resource_problem(
    *, model_names: frozenset[str], companions: frozenset[ResourceIdentity]
) -> tuple[str, str]:
    if len(model_names) == 1:
        model_name: str = next(iter(model_names))
        return (
            f"checks only model '{model_name}'; singular audits must be cross-resource",
            f"attach a generic audit to '{model_name}' instead: write it in an audits/generic/ "
            "role and select FROM @relation, joining @relation to itself for self-join checks",
        )
    if companions:
        return (
            "checks only sources or seeds; singular audits must reference at least one model",
            "attach YAML audits to the source or seed instead",
        )
    return (
        "references no SQLBuild resource; singular audits must reference two or more models, or "
        "a model plus a source, seed, or table function via "
        f"{SqlReferenceKind.REF.placeholder_call()}, {SqlReferenceKind.SOURCE.placeholder_call()}, "
        f"or {SqlReferenceKind.SEED.placeholder_call()}",
        "reference resources through SQLBuild calls instead of hard-coded relation names, or "
        "attach a generic audit to the resource being checked",
    )


def merge_audit_arguments(
    *,
    owner_file: Path,
    definition_name: str,
    implicit_arguments: dict[str, object],
    explicit_arguments: dict[str, object],
) -> dict[str, object]:
    """Merge implicit attached-audit arguments with explicit authored arguments."""

    merged_arguments: dict[str, object] = dict(implicit_arguments)
    argument_name: str
    argument_value: object
    for argument_name, argument_value in explicit_arguments.items():
        if (
            argument_name in implicit_arguments
            and implicit_arguments[argument_name] != argument_value
        ):
            raise CompileInputError(
                f"{owner_file} audit '{definition_name}' must not override implicit "
                f"{argument_name} from attached context"
            )
        merged_arguments[argument_name] = argument_value
    return merged_arguments


def render_generic_audit_sql(
    *,
    sql: str,
    arguments: dict[str, object],
    owner_file: Path,
    definition_name: str,
) -> str:
    """Render generic attached-audit parameters into executable SQL text."""

    return render_parameterized_sql(
        sql=sql,
        arguments=arguments,
        owner_label=str(owner_file),
        definition_label=f"generic audit '{definition_name}'",
    )


def resolve_audit_severity(
    *,
    instance_severity: str | AuditSeverity | None,
    default_severity: str | AuditSeverity | None,
    audit_label: str,
) -> AuditSeverity:
    """Resolve audit severity from instance, project default, or error fallback."""

    valid_values: tuple[str, ...] = tuple(severity.value for severity in AuditSeverity)
    if instance_severity is not None:
        try:
            return AuditSeverity(instance_severity)
        except ValueError as error:
            raise CompileInputError(
                f"{audit_label}: unknown severity '{instance_severity}'; "
                f"valid values: {', '.join(valid_values)}"
            ) from error
    if default_severity is not None:
        try:
            return AuditSeverity(default_severity)
        except ValueError as error:
            raise CompileInputError(
                "settings.default_audit_severity in sqlbuild_project.toml: "
                f"unknown value '{default_severity}'; valid values: {', '.join(valid_values)}"
            ) from error
    return AuditSeverity.ERROR


def measurement_policy_severity(thresholds: MeasurementThresholds) -> AuditSeverity:
    """Return the effective scheduling severity for a measurement policy."""

    return AuditSeverity.ERROR if thresholds.error is not None else AuditSeverity.WARN


def resolve_audit_run_scope(
    *,
    instance_run_scope: str | None,
    default_run_scope: str | None,
) -> str:
    """Resolve audit run scope from instance, project default, or delta/final fallback."""

    from sqlbuild.compiler.auditing.types import AuditRunScope

    valid_values: frozenset[str] = frozenset(s.value for s in AuditRunScope)
    if instance_run_scope is not None:
        if instance_run_scope not in valid_values:
            raise CompileInputError(
                f"unknown audit run_scope '{instance_run_scope}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return instance_run_scope
    if default_run_scope is not None:
        if default_run_scope not in valid_values:
            raise CompileInputError(
                f"settings.default_audit_run_scope in sqlbuild_project.toml: "
                f"unknown value '{default_run_scope}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return default_run_scope
    return AuditRunScope.DELTA_AND_FINAL


def validate_model_attached_audit_references(
    *,
    references: tuple[CompileSqlReference, ...],
    attached_target_kind: str,
    attached_target_name: str,
    audit_label: str,
) -> None:
    """Validate that a model-attached generic audit references the attached model."""

    if attached_target_kind != AttachedAuditTargetKind.MODEL:
        return
    ref_names: frozenset[str] = frozenset(
        ref.ref_name for ref in references if ref.ref_kind == SqlReferenceKind.REF
    )
    if attached_target_name not in ref_names:
        raise CompileInputError(
            f"{audit_label}: model-attached audit must reference the attached model "
            f"'{attached_target_name}' via {SqlReferenceKind.REF.placeholder_call()}"
        )


def _str_from_dict(*, values: dict[str, object], key: str) -> str | None:
    """Extract a string value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, str) else None


def _bool_from_dict(*, values: dict[str, object], key: str) -> bool:
    """Extract a bool value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, bool) else False


def _argument_references(
    *expansions: AuthoredSqlExpansionResult | None,
) -> tuple[CompileSqlReference, ...]:
    references: list[CompileSqlReference] = []
    for expansion in expansions:
        if expansion is not None:
            references.extend(expansion.argument_references)
    return tuple(references)


def _combined_references(
    *sql_values: str | None, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlReference, ...]:
    """Extract references from independently compiled measurement/evidence queries."""

    references: list[CompileSqlReference] = []
    for sql in sql_values:
        if sql is not None:
            references.extend(extract_sql_references(sql=sql, syntax=syntax))
    return tuple(dict.fromkeys(references))
