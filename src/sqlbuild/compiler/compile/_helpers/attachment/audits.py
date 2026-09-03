"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    validate_audit_references,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.arguments import (
    render_parameterized_sql,
    render_sql_argument_value,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_expansion
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql_result,
)
from sqlbuild.compiler.compile.constants import (
    AUDIT_DIRECTORY_NAME,
    GENERIC_AUDIT_DIRECTORY_NAME,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileAuditInput,
    CompileModelInput,
    CompileSourceInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SchemaColumn,
    SettingsConfig,
    SourceColumnEntry,
)


@dataclass(frozen=True)
class _AuditAttachmentContext:
    """Run-constant inputs shared across attached audit rendering."""

    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    loaded_macros: dict[str, LoadedMacro]
    known_model_names: set[str]
    known_seed_names: set[str]
    known_source_names: set[str]
    default_audit_severity: str | None
    default_audit_run_scope: str | None
    effective_vars: dict[str, object]
    macro_context: MacroContext
    declaration_expansion: DeclarationExpansionContext


_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def build_audit_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_settings: SettingsConfig,
    model_inputs: tuple[CompileModelInput, ...],
    source_inputs: tuple[CompileSourceInput, ...],
    effective_vars: dict[str, object],
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    | None = None,
) -> tuple[CompileAuditInput, ...]:
    """Build compile-time audit inputs from discovered SQL audit blocks."""

    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    if generic_audit_definitions is None:
        generic_audit_definitions = index_generic_audit_definitions(discovered_inputs.audit_files)
    default_audit_severity: str | None = effective_settings.default_audit_severity
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
    )
    audit_inputs: list[CompileAuditInput] = []
    audit_file: DiscoveredAuditFile
    for audit_file in discovered_inputs.audit_files:
        if is_generic_audit_file(audit_file):
            continue
        audit_block: DiscoveredAuditBlock
        for audit_block in audit_file.blocks:
            scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
                context=declaration_expansion,
                file_path=audit_file.file_path,
                resource=ResourceIdentity(
                    ResourceKind.AUDIT,
                    audit_block.name or audit_file.relative_path.stem,
                ),
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
            reject_cursor_intrinsics(
                sql=expanded_sql_body,
                context=f"Audit '{audit_block.name or audit_file.file_path.stem}'",
            )
            references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_sql_body)
            validate_audit_references(
                references=references,
                audit_file=audit_file,
                known_model_names=known_model_names,
                known_seed_names=known_seed_names,
                known_source_names=known_source_names,
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
            resolved_severity: str = resolve_audit_severity(
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
                    references=references,
                    severity=resolved_severity,
                    run_scope=resolved_run_scope,
                    always_run=header_always_run,
                    declaration_usages=expansion.usages,
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
    attached_audit_inputs: list[CompileAuditInput] = []
    audit_instance: SchemaAuditInstance
    for audit_instance in model_input.schema_entry.audits:
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
                attached_column_name=None,
                context=context,
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
                )
            )
    return tuple(attached_audit_inputs)


def build_source_attached_audit_inputs(
    *,
    source_input: CompileSourceInput,
    context: _AuditAttachmentContext,
) -> tuple[CompileAuditInput, ...]:
    """Render source-attached audits into compile audit inputs."""

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
                )
            )
    return tuple(attached_audit_inputs)


def build_attached_audit_input(
    *,
    audit_instance: SchemaAuditInstance,
    owner_file: Path,
    implicit_arguments: dict[str, object],
    attached_target_kind: str,
    attached_target_name: str,
    attached_column_name: str | None,
    context: _AuditAttachmentContext,
) -> CompileAuditInput:
    """Render one attached generic audit instance into a compile audit input."""

    definition: tuple[DiscoveredAuditFile, DiscoveredAuditBlock] | None = (
        context.generic_audit_definitions.get(audit_instance.definition_name)
    )
    if definition is None:
        raise CompileInputError(
            f"{owner_file} references unknown generic audit '{audit_instance.definition_name}'"
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
    scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
        context=context.declaration_expansion,
        file_path=definition[0].file_path,
        resource=ResourceIdentity(
            ResourceKind.AUDIT,
            definition[1].name or definition[0].relative_path.stem,
        ),
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
    reject_cursor_intrinsics(
        sql=expanded_sql_body,
        context=f"Audit '{audit_instance.definition_name}'",
    )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_sql_body)
    validate_audit_references(
        references=references,
        audit_file=definition[0],
        known_model_names=context.known_model_names,
        known_seed_names=context.known_seed_names,
        known_source_names=context.known_source_names,
    )
    audit_label: str = f"{owner_file} audit '{audit_instance.definition_name}'"
    resolved_severity: str = resolve_audit_severity(
        instance_severity=audit_instance.severity,
        default_severity=context.default_audit_severity,
        audit_label=audit_label,
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
        name=audit_instance.name,
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        attached_column_name=attached_column_name,
        severity=resolved_severity,
        run_scope=resolved_run_scope,
        always_run=audit_instance.always_run,
        declaration_usages=expansion.usages,
    )


def index_generic_audit_definitions(
    audit_files: tuple[DiscoveredAuditFile, ...],
) -> dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]:
    """Index generic audit definitions discovered under audits/generic/."""

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
        definition_name: str = audit_file.file_path.stem
        if definition_name in definitions:
            raise CompileInputError(
                f"Duplicate generic audit definition found for '{definition_name}'"
            )
        definitions[definition_name] = (audit_file, audit_file.blocks[0])
    return definitions


def is_generic_audit_file(audit_file: DiscoveredAuditFile) -> bool:
    """Return whether a discovered audit file is a generic definition."""

    return audit_file.relative_path.parts[:2] == (
        AUDIT_DIRECTORY_NAME,
        GENERIC_AUDIT_DIRECTORY_NAME,
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


def render_generic_audit_argument(
    *,
    argument_name: str,
    arguments: dict[str, object],
    owner_file: Path,
    definition_name: str,
    quoted: bool,
) -> str:
    """Render one generic attached-audit parameter value into SQL text."""

    return render_parameterized_sql(
        sql=f"@'{argument_name}'" if quoted else f"@{argument_name}",
        arguments=arguments,
        owner_label=str(owner_file),
        definition_label=f"generic audit '{definition_name}'",
    )


def render_generic_audit_argument_value(
    *,
    argument_value: object,
    owner_file: Path,
    definition_name: str,
    argument_name: str,
    quoted: bool,
) -> str:
    """Render one generic attached-audit argument value using raw or literal SQL rules."""

    return render_sql_argument_value(
        argument_value=argument_value,
        owner_label=str(owner_file),
        definition_label=f"audit '{definition_name}'",
        argument_name=argument_name,
        quoted=quoted,
    )


def resolve_audit_severity(
    *,
    instance_severity: str | None,
    default_severity: str | None,
    audit_label: str,
) -> str:
    """Resolve audit severity from instance, project default, or error fallback."""

    from sqlbuild.compiler.auditing.types import AuditSeverity

    valid_values: frozenset[str] = frozenset(s.value for s in AuditSeverity)
    if instance_severity is not None:
        if instance_severity not in valid_values:
            raise CompileInputError(
                f"{audit_label}: unknown severity '{instance_severity}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return instance_severity
    if default_severity is not None:
        if default_severity not in valid_values:
            raise CompileInputError(
                f"settings.default_audit_severity in sqlbuild_project.toml: "
                f"unknown value '{default_severity}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return default_severity
    return AuditSeverity.ERROR


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
