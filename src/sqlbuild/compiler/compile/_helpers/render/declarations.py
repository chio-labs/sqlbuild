"""Compile-time resolution for enum and constant declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import MappingProxyType

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import MACRO_TOKEN, SQL_QUOTE_TOKENS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationExpansionContext,
    DeclarationExpansionResult,
    DeclarationResolutionContext,
    DeclarationRuntimeProjection,
    DeclarationScopeResolver,
    ExpansionSpan,
    LoadedMacro,
)
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredModelSchemaFile,
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.frontier.main._native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main._report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.model_loop.main._build_native_declaration_contexts import (
    build_native_declaration_contexts,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    ScopeKind,
    UsageKind,
)
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn, SchemaModelEntry
from sqlbuild.sql_values.exceptions import SqlValueRenderingError, SqlValueValidationError
from sqlbuild.sql_values.main.validate_rendered_size import validate_rendered_sql_value_size
from sqlbuild.sql_values.types import CollectionRendering, SqlValueKind

_ENUM_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"@enum\s*\(\s*(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)\s*\)\s*\.\s*(?P<member>[A-Za-z_][A-Za-z0-9_]*)"
)
_CONSTANT_REFERENCE_PATTERN: re.Pattern[str] = re.compile(
    r"@const\s*\(\s*(?P<quote>['\"])(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)\s*\)"
)
_DECLARATION_REFERENCE_START_PATTERN: re.Pattern[str] = re.compile(r"@(?P<kind>enum|const)\b")
_DECLARATION_SCAN_SPECIAL: re.Pattern[str] = re.compile(r"['\"`$@/-]")
_CONTEXT: str = "Enum and constant expansion"
_ACCEPTED_VALUES_AUDIT: str = "accepted_values"
_ENUM_REFERENCE_KIND: str = "enum"
_CONSTANT_REFERENCE_KIND: str = "const"


def build_public_declaration_indexes(
    *, discovered_inputs: DiscoveredProjectInputs
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]:
    """Build collision-checked indexes of every public declaration."""

    enums: dict[str, EnumDeclaration] = {}
    constants: dict[str, ConstantDeclaration] = {}
    enum_file: DiscoveredEnumFile
    for enum_file in discovered_inputs.enum_files:
        declaration: EnumDeclaration
        for declaration in enum_file.declarations:
            enums = _with_declaration(
                declarations=enums,
                declaration=declaration,
                kind="enum",
            )
    constant_file: DiscoveredConstantFile
    for constant_file in discovered_inputs.constant_files:
        constant_declaration: ConstantDeclaration
        for constant_declaration in constant_file.declarations:
            constants = _with_declaration(
                declarations=constants,
                declaration=constant_declaration,
                kind="constant",
            )
    return enums, constants


def build_declaration_scope_resolver(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    scope_index: ScopeIndex,
    loaded_macros: Mapping[str, LoadedMacro] | None = None,
    lookup: ScopeLookup | None = None,
) -> DeclarationScopeResolver:
    """Pair the serializable static index with original process-local declaration values."""

    declarations: dict[
        DeclarationIdentity, EnumDeclaration | ConstantDeclaration | LoadedMacro
    ] = {}
    enum_file: DiscoveredEnumFile
    for enum_file in discovered_inputs.enum_files:
        for declaration in enum_file.declarations:
            declarations[DeclarationIdentity(DeclarationKind.ENUM, declaration.name)] = declaration
    constant_file: DiscoveredConstantFile
    for constant_file in discovered_inputs.constant_files:
        for declaration in constant_file.declarations:
            declarations[DeclarationIdentity(DeclarationKind.CONSTANT, declaration.name)] = (
                declaration
            )
    for model_file in discovered_inputs.model_files:
        model_name_value: object = model_file.header_values.get("name")
        model_name: str = (
            model_name_value
            if isinstance(model_name_value, str) and model_name_value
            else model_file.relative_path.stem
        )
        owner: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, model_name)
        for declaration in model_file.enum_declarations:
            declarations[DeclarationIdentity(DeclarationKind.ENUM, declaration.name, owner)] = (
                declaration
            )
        for declaration in model_file.constant_declarations:
            declarations[DeclarationIdentity(DeclarationKind.CONSTANT, declaration.name, owner)] = (
                declaration
            )
    if loaded_macros is not None:
        for macro in loaded_macros.values():
            declarations[DeclarationIdentity(DeclarationKind.MACRO, macro.name)] = macro
    if lookup is None and native_stage_enabled(NativeStage.DECLARATION_SCOPES):
        report_native_fallback(site=NativeFallbackSite.SCOPE_REBIND_LOOKUP)
    scope_lookup: ScopeLookup = build_scope_lookup(index=scope_index) if lookup is None else lookup
    return DeclarationScopeResolver(
        project_dir=discovered_inputs.project_dir,
        lookup=scope_lookup,
        projection=DeclarationRuntimeProjection(declarations=MappingProxyType(declarations)),
        resource_specific=frozenset(
            declaration.identity.owner
            for declaration in scope_index.declarations
            if declaration.scope is ScopeKind.PRIVATE and declaration.identity.owner is not None
        )
        | frozenset(grant.resource for grant in scope_index.grants),
        native_contexts=build_native_declaration_contexts(
            lookup=scope_lookup, declarations=declarations
        ),
    )


def resolve_declaration_context(
    *,
    resolver: DeclarationScopeResolver,
    file_path: Path,
    resource: ResourceIdentity | None = None,
) -> DeclarationResolutionContext:
    """Project canonical visibility for one authored path onto runtime declaration values."""

    context: DeclarationResolutionContext
    projected: bool
    context, projected = resolver.native_contexts.resolve(resolver, file_path, resource)
    if projected:
        report_native_answer(stage=NativeStage.MODEL_LOOP, kind="declaration_contexts")
    return context


def declaration_usage_records(
    *, sql: str, resource: ResourceIdentity, declarations: DeclarationResolutionContext
) -> tuple[UsageRecord, ...]:
    """Collect declaration usages with path or expected-model provenance."""

    usages: list[UsageRecord] = []
    cursor: int = 0
    while (reference_start := _find_next_reference_start(sql=sql, start=cursor)) is not None:
        start_match: re.Match[str] | None = _DECLARATION_REFERENCE_START_PATTERN.match(
            sql, reference_start
        )
        if start_match is None:
            break
        is_enum: bool = start_match.group("kind") == _ENUM_REFERENCE_KIND
        match: re.Match[str] | None = (
            _ENUM_REFERENCE_PATTERN.match(sql, reference_start)
            if is_enum
            else _CONSTANT_REFERENCE_PATTERN.match(sql, reference_start)
        )
        if match is None:
            cursor = start_match.end()
            continue
        name: str = match.group("name")
        visibility: tuple[VisibilityRecord, ...] = (
            declarations.enum_visibility.get(name, ())
            if is_enum
            else declarations.constant_visibility.get(name, ())
        )
        for record in usage_visibility(visibility=visibility, consumer=resource):
            usages.append(
                UsageRecord(
                    consumer=resource,
                    declaration=record.declaration,
                    kind=UsageKind.RUNTIME,
                    through=record.through,
                )
            )
        cursor = match.end()
    return tuple(dict.fromkeys(usages))


def resolve_declaration_expansion(
    *,
    context: DeclarationExpansionContext,
    file_path: Path,
    resource: ResourceIdentity | None = None,
) -> DeclarationExpansionContext:
    """Return an expansion context scoped to one authored resource path."""

    if context.resolver is None or not context.resolver.lookup.index.declarations:
        return context
    return replace(
        context,
        declarations=resolve_declaration_context(
            resolver=context.resolver,
            file_path=file_path,
            resource=resource,
        ),
    )


def build_model_declaration_indexes(
    *, model_file: DiscoveredSqlModelFile
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]:
    """Build collision-checked declaration indexes private to one model."""

    return (
        {declaration.name: declaration for declaration in model_file.enum_declarations},
        {declaration.name: declaration for declaration in model_file.constant_declarations},
    )


def build_public_model_schema_index(
    *, discovered_inputs: DiscoveredProjectInputs
) -> dict[str, ModelSchemaDeclaration]:
    """Build and resolve the collision-checked public model-schema index."""

    authored: dict[str, ModelSchemaDeclaration] = {}
    schema_file: DiscoveredModelSchemaFile
    for schema_file in discovered_inputs.model_schema_files:
        declaration: ModelSchemaDeclaration
        for declaration in schema_file.declarations:
            existing: ModelSchemaDeclaration | None = authored.get(declaration.name)
            if existing is not None:
                raise CompileInputError(
                    f"Duplicate public schema '{declaration.name}' in "
                    f"{existing.relative_path} and {declaration.relative_path}"
                )
            authored[declaration.name] = declaration

    resolved: dict[str, ModelSchemaDeclaration] = {}
    for schema_name in authored:
        _declaration: ModelSchemaDeclaration
        _declaration, resolved = _resolve_model_schema_declaration(
            name=schema_name,
            authored=authored,
            resolved=resolved,
            resolving=(),
        )
    return resolved


def _resolve_model_schema_declaration(
    *,
    name: str,
    authored: dict[str, ModelSchemaDeclaration],
    resolved: dict[str, ModelSchemaDeclaration],
    resolving: tuple[str, ...],
) -> tuple[ModelSchemaDeclaration, dict[str, ModelSchemaDeclaration]]:
    existing_resolved: ModelSchemaDeclaration | None = resolved.get(name)
    if existing_resolved is not None:
        return existing_resolved, resolved
    if name in resolving:
        cycle_start: int = resolving.index(name)
        cycle: str = " -> ".join((*resolving[cycle_start:], name))
        raise CompileInputError(f"Model schema inheritance cycle: {cycle}")
    declaration: ModelSchemaDeclaration = authored[name]
    inherited_columns: tuple[SchemaColumn, ...] = ()
    if declaration.extends is not None:
        parent: ModelSchemaDeclaration | None = authored.get(declaration.extends)
        if parent is None:
            raise CompileInputError(
                f"Schema '{name}' in {declaration.relative_path} extends unknown schema "
                f"'{declaration.extends}'"
            )
        resolved_parent: ModelSchemaDeclaration
        resolved_parent, resolved = _resolve_model_schema_declaration(
            name=parent.name,
            authored=authored,
            resolved=resolved,
            resolving=(*resolving, name),
        )
        inherited_columns = resolved_parent.columns
    _validate_no_inherited_column_overrides(
        declaration=declaration,
        inherited_columns=inherited_columns,
    )
    resolved_declaration: ModelSchemaDeclaration = replace(
        declaration,
        columns=(*inherited_columns, *declaration.columns),
    )
    return resolved_declaration, resolved | {name: resolved_declaration}


def _validate_no_inherited_column_overrides(
    *,
    declaration: ModelSchemaDeclaration,
    inherited_columns: tuple[SchemaColumn, ...],
) -> None:
    inherited_by_name: dict[str, SchemaColumn] = {
        column.name.lower(): column for column in inherited_columns
    }
    local_column: SchemaColumn
    for local_column in declaration.columns:
        inherited: SchemaColumn | None = inherited_by_name.get(local_column.name.lower())
        if inherited is None:
            continue
        inherited_origin: str = (
            f"{inherited.location.path}:{inherited.location.line}"
            if inherited.location is not None
            else "an ancestor schema"
        )
        raise CompileInputError(
            f"Schema '{declaration.name}' in {declaration.relative_path} redeclares inherited "
            f"column '{local_column.name}' from {inherited_origin}; column overrides are not "
            "supported"
        )


def expand_scanned_declaration_references(  # noqa: PLR0913
    *,
    sql: str,
    references: NativeDeclarationScan,
    file_path: Path,
    declarations: DeclarationResolutionContext,
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
) -> DeclarationExpansionResult:
    """Splice natively scanned references and raise the first error the scan stopped at."""

    scanned, stop = references
    if not scanned and stop is None:
        return DeclarationExpansionResult(sql=sql, spans=(), usages=())
    consumer: ResourceIdentity | DeclarationIdentity | None = declarations.consumer
    expanded_sql, spans, usages = _native.expand_declaration_references(
        (sql, list(scanned), stop),
        declarations,
        (
            consumer,
            isinstance(consumer, ResourceIdentity)
            and consumer.kind in {ResourceKind.TEST, ResourceKind.SCENARIO},
            str(file_path),
        ),
        (
            partial(
                render_constant_declaration,
                value_renderer=value_renderer,
                collection_rendering=collection_rendering,
                file_path=file_path,
            ),
            {"usage_record": UsageRecord, "compile_error": CompileInputError},
        ),
    )
    return DeclarationExpansionResult(
        sql=expanded_sql,
        spans=tuple(ExpansionSpan(*span) for span in spans),
        usages=tuple(dict.fromkeys(usages)),
    )


def usage_visibility(
    *,
    visibility: tuple[VisibilityRecord, ...],
    consumer: ResourceIdentity | DeclarationIdentity,
) -> tuple[VisibilityRecord, ...]:
    if not isinstance(consumer, ResourceIdentity) or consumer.kind not in {
        ResourceKind.TEST,
        ResourceKind.SCENARIO,
    }:
        return visibility
    relationship_visibility: tuple[VisibilityRecord, ...] = tuple(
        record for record in visibility if record.through is not None
    )
    return relationship_visibility or visibility


def resolve_enum_contract_columns(
    *,
    schema_entry: SchemaModelEntry | None,
    config_values: dict[str, object],
    enums: dict[str, EnumDeclaration],
) -> tuple[SchemaModelEntry | None, dict[str, EnumDeclaration]]:
    """Resolve enum column types and synthesize enforced accepted-values audits."""

    if schema_entry is None:
        return None, {}
    contract_enforced: bool = config_values.get("contract") == ContractPolicy.ENFORCED
    enum_columns: dict[str, EnumDeclaration] = {}
    columns: list[SchemaColumn] = []
    column: SchemaColumn
    for column in schema_entry.columns:
        declaration: EnumDeclaration | None = enums.get(column.type or "")
        if declaration is None:
            columns.append(column)
            continue
        enum_columns[column.name] = declaration
        audits: tuple[SchemaAuditInstance, ...] = column.audits
        if contract_enforced:
            generated_audit: SchemaAuditInstance = SchemaAuditInstance(
                definition_name=_ACCEPTED_VALUES_AUDIT,
                arguments={"values": tuple(member.value for member in declaration.members)},
            )
            if generated_audit not in audits:
                audits = (*audits, generated_audit)
        columns.append(replace(column, type=declaration.scalar_type, audits=audits))
    return replace(schema_entry, columns=tuple(columns)), enum_columns


def _with_declaration[T: EnumDeclaration | ConstantDeclaration](
    *, declarations: dict[str, T], declaration: T, kind: str
) -> dict[str, T]:
    existing: T | None = declarations.get(declaration.name)
    if existing is not None:
        raise CompileInputError(
            f"Duplicate public {kind} '{declaration.name}' in {existing.relative_path} and "
            f"{declaration.relative_path}"
        )
    return declarations | {declaration.name: declaration}


def render_constant_declaration(
    *,
    declaration: ConstantDeclaration,
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
    file_path: Path | None = None,
) -> str:
    """Render one validated constant with the active adapter's typed-value contract."""

    selected_rendering: CollectionRendering = declaration.render_as or collection_rendering
    try:
        if declaration.value.kind in {
            SqlValueKind.STRING,
            SqlValueKind.INTEGER,
            SqlValueKind.BOOLEAN,
            SqlValueKind.FLOAT,
            SqlValueKind.DECIMAL,
            SqlValueKind.NULL,
        }:
            rendered: str = value_renderer.render_typed_scalar(value=declaration.value)
        elif declaration.value.kind in {SqlValueKind.LIST, SqlValueKind.SET}:
            rendered = (
                value_renderer.render_typed_array(value=declaration.value)
                if selected_rendering == CollectionRendering.ARRAY
                else value_renderer.render_typed_value_list(value=declaration.value)
            )
        else:
            rendered = value_renderer.render_typed_object(value=declaration.value)
        validate_rendered_sql_value_size(
            rendered_sql=rendered,
            context=f"{declaration.relative_path} constant '{declaration.name}'",
        )
    except (SqlValueRenderingError, SqlValueValidationError) as error:
        raise CompileInputError(
            f"{declaration.relative_path} constant '{declaration.name}' could not be rendered "
            f"in '{file_path or declaration.relative_path}' by adapter "
            f"'{value_renderer.adapter_name}' as "
            f"{selected_rendering.value}: {error}",
        ) from error
    return rendered


def render_enum_member_value(*, value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"


def _find_next_reference_start(*, sql: str, start: int) -> int | None:
    if sql.find("@enum", start) < 0 and sql.find("@const", start) < 0:
        return None
    index: int = start
    while index < len(sql):
        special: re.Match[str] | None = _DECLARATION_SCAN_SPECIAL.search(sql, index)
        if special is None:
            return None
        index = special.start()
        character: str = sql[index]
        if character in SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if character == MACRO_TOKEN and _DECLARATION_REFERENCE_START_PATTERN.match(sql, index):
            return index
        index += 1
    return None
