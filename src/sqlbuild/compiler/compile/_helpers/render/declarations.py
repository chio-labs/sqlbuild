"""Compile-time resolution for enum and constant declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

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
    EnumMember,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.model_loop.constants import (
    ENUM_REFERENCE_KIND_CODE,
    INVALID_CONSTANT_REFERENCE_STOP_CODE,
    INVALID_ENUM_REFERENCE_STOP_CODE,
    UNCLOSED_BLOCK_COMMENT_STOP_CODE,
)
from sqlbuild.compiler.model_loop.main._build_native_declaration_contexts import (
    build_native_declaration_contexts,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.scopes.constants import CURRENT_PATH_COMPONENT, QUALIFIED_IDENTITY_SEPARATOR
from sqlbuild.compiler.scopes.main._declaration_lexical_path import declaration_lexical_path
from sqlbuild.compiler.scopes.main._resolve_scope_declaration_visibility import (
    resolve_scope_declaration_visibility,
)
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    ScopeLookup,
    ScopeTargetQuery,
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
_PATH_CACHE_PREFIX: str = "<path>"


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

    target_path: Path = file_path
    if resolver.project_dir is not None and file_path.is_absolute():
        try:
            target_path = file_path.relative_to(resolver.project_dir)
        except ValueError:
            target_path = file_path
    resources: tuple[ResourceRecord, ...] = (
        resolver.lookup.resources.get(resource, ())
        if resource is not None
        else resolver.lookup.resources_by_path.get(target_path.as_posix(), ())
    )
    cache_key: tuple[str, str] | None = None
    if (
        len(resources) == 1
        and resolver.resource_specific is not None
        and resources[0].identity not in resolver.resource_specific
    ):
        cache_key = (Path(resources[0].path).parent.as_posix(), resources[0].ownership_root.path)
        cached: DeclarationResolutionContext | None = resolver.contexts_by_directory.get(cache_key)
        if cached is not None:
            return _rebind_declaration_context(context=cached, consumer=resources[0].identity)
    elif not resources and resource is None:
        cache_key = (_PATH_CACHE_PREFIX, target_path.as_posix())
        cached_path_context: DeclarationResolutionContext | None = (
            resolver.contexts_by_directory.get(cache_key)
        )
        if cached_path_context is not None:
            return cached_path_context
    matches: tuple[ResourceRecord, ...] = resources
    consumer: ResourceIdentity | None = resource or (resources[0].identity if resources else None)
    if not resources or _scope_query_parses_identity(resource=resource, target_path=target_path):
        matches, consumer = _queried_matches(
            resolver=resolver, target_path=target_path, resource=resource
        )
    context: DeclarationResolutionContext = resolver.native_contexts.context(
        list(matches), consumer
    )
    if cache_key is not None:
        resolver.cache_context(key=cache_key, context=context)
    return context


def _scope_query_parses_identity(*, resource: ResourceIdentity | None, target_path: Path) -> bool:
    """Whether the scope query reads the path target as a qualified identity."""

    return resource is None and QUALIFIED_IDENTITY_SEPARATOR in str(target_path)


def _queried_matches(
    *,
    resolver: DeclarationScopeResolver,
    target_path: Path,
    resource: ResourceIdentity | None,
) -> tuple[tuple[ResourceRecord, ...], ResourceIdentity | None]:
    """The resources a scope query matches, or an unknown path's lexical folder record."""

    query: ScopeTargetQuery = resolve_scope_declaration_visibility(
        lookup=resolver.lookup, target=resource or target_path
    ).target
    if not query.unknown:
        return query.matches, resource or (query.matches[0].identity if query.matches else None)
    definition_record: DeclarationRecord | None = next(
        (
            record
            for record in resolver.lookup.index.declarations
            if record.path == target_path.as_posix() and record.scope is not ScopeKind.PRIVATE
        ),
        None,
    )
    lexical_path: str = (
        Path(declaration_lexical_path(record=definition_record)).as_posix()
        if definition_record is not None
        else target_path.as_posix()
    )
    return (
        ResourceRecord(
            identity=ResourceIdentity(ResourceKind.MODEL, f"<path:{lexical_path}>"),
            path=lexical_path,
            ownership_root=OwnershipRoot(path=CURRENT_PATH_COMPONENT),
        ),
    ), None


def _rebind_declaration_context(
    *, context: DeclarationResolutionContext, consumer: ResourceIdentity
) -> DeclarationResolutionContext:
    return replace(
        context,
        consumer=consumer,
        enums=dict(context.enums),
        constants=dict(context.constants),
        macros=dict(context.macros),
        macro_records=dict(context.macro_records),
        inaccessible_enums=dict(context.inaccessible_enums),
        inaccessible_constants=dict(context.inaccessible_constants),
        inaccessible_macros=dict(context.inaccessible_macros),
        enum_visibility=_rebind_visibility(
            records_by_name=context.enum_visibility, consumer=consumer
        ),
        constant_visibility=_rebind_visibility(
            records_by_name=context.constant_visibility, consumer=consumer
        ),
        macro_visibility=_rebind_visibility(
            records_by_name=context.macro_visibility, consumer=consumer
        ),
    )


def _rebind_visibility(
    *, records_by_name: dict[str, tuple[VisibilityRecord, ...]], consumer: ResourceIdentity
) -> dict[str, tuple[VisibilityRecord, ...]]:
    result: dict[str, tuple[VisibilityRecord, ...]] = {}
    for name, records in records_by_name.items():
        result[name] = tuple(replace(record, resource=consumer) for record in records)
    return result


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


def declaration_reference_usages(
    *,
    declarations: DeclarationResolutionContext,
    visibility: tuple[VisibilityRecord, ...],
    enum_member: str | None,
) -> tuple[UsageRecord, ...]:
    """Usage records one resolved `@enum`/`@const` reference adds for the context's consumer."""

    consumer: ResourceIdentity | DeclarationIdentity | None = declarations.consumer
    if consumer is None:
        return ()
    return tuple(
        UsageRecord(
            consumer=consumer,
            declaration=visible.declaration,
            through=visible.through,
            enum_member=enum_member,
        )
        for visible in usage_visibility(visibility=visibility, consumer=consumer)
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
    parts: list[str] = []
    spans: list[ExpansionSpan] = []
    usages: list[UsageRecord] = []
    cursor: int = 0
    output_length: int = 0
    for kind, name, member, start, end in scanned:
        replacement: str
        visibility: tuple[VisibilityRecord, ...]
        if kind == ENUM_REFERENCE_KIND_CODE:
            replacement = _enum_member_text(
                name=name,
                member_name=cast(str, member),
                file_path=file_path,
                enums=declarations.enums,
                inaccessible_enums=declarations.inaccessible_enums,
            )
            visibility = declarations.enum_visibility.get(name, ())
        else:
            replacement = _constant_text(
                name=name,
                file_path=file_path,
                constants=declarations.constants,
                inaccessible_constants=declarations.inaccessible_constants,
                value_renderer=value_renderer,
                collection_rendering=collection_rendering,
            )
            visibility = declarations.constant_visibility.get(name, ())
        parts.append(sql[cursor:start])
        output_length += start - cursor
        usages.extend(
            declaration_reference_usages(
                declarations=declarations, visibility=visibility, enum_member=member
            )
        )
        parts.append(replacement)
        spans.append(
            ExpansionSpan(
                source_start=start,
                source_end=end,
                output_start=output_length,
                output_end=output_length + len(replacement),
            )
        )
        output_length += len(replacement)
        cursor = end
    if stop is not None:
        raise CompileInputError(_stop_message(stop=stop, file_path=file_path))
    parts.append(sql[cursor:])
    return DeclarationExpansionResult(
        sql="".join(parts), spans=tuple(spans), usages=tuple(dict.fromkeys(usages))
    )


def _stop_message(*, stop: int, file_path: Path) -> str:
    if stop == INVALID_ENUM_REFERENCE_STOP_CODE:
        return _invalid_reference_message(kind=_ENUM_REFERENCE_KIND, file_path=file_path)
    if stop == INVALID_CONSTANT_REFERENCE_STOP_CODE:
        return _invalid_reference_message(kind=_CONSTANT_REFERENCE_KIND, file_path=file_path)
    if stop == UNCLOSED_BLOCK_COMMENT_STOP_CODE:
        return f"{_CONTEXT} contains an unclosed block comment"
    return f"{_CONTEXT} contains an unclosed quoted string"


def _invalid_reference_message(*, kind: str, file_path: Path) -> str:
    noun: str = "enum" if kind == _ENUM_REFERENCE_KIND else "constant"
    return f"Invalid {noun} reference in '{file_path}'"


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


def _enum_member_text(
    *,
    name: str,
    member_name: str,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    inaccessible_enums: dict[str, DeclarationRecord],
) -> str:
    declaration: EnumDeclaration | None = enums.get(name)
    if declaration is None:
        inaccessible: DeclarationRecord | None = inaccessible_enums.get(name)
        if inaccessible is not None:
            raise CompileInputError(
                _inaccessible_declaration_message(
                    kind="enum", name=name, record=inaccessible, consumer=file_path
                ),
            )
        scope_help: str = " in this model" if name.startswith("_") else ""
        visible: str = ", ".join(sorted(enums)) or "none"
        raise CompileInputError(
            f"Unknown enum '{name}'{scope_help} in '{file_path}'. Visible enums: {visible}",
        )
    member: EnumMember | None = next(
        (candidate for candidate in declaration.members if candidate.name == member_name),
        None,
    )
    if member is None:
        available: str = ", ".join(item.name for item in declaration.members)
        raise CompileInputError(
            f"Unknown member '{member_name}' for enum '{name}' in '{file_path}'. "
            f"Available members: {available}",
        )
    return render_enum_member_value(value=member.value)


def _constant_text(
    *,
    name: str,
    file_path: Path,
    constants: dict[str, ConstantDeclaration],
    inaccessible_constants: dict[str, DeclarationRecord],
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
) -> str:
    declaration: ConstantDeclaration | None = constants.get(name)
    if declaration is None:
        inaccessible: DeclarationRecord | None = inaccessible_constants.get(name)
        if inaccessible is not None:
            raise CompileInputError(
                _inaccessible_declaration_message(
                    kind="constant", name=name, record=inaccessible, consumer=file_path
                ),
            )
        scope_help: str = " in this model" if name.startswith("_") else ""
        visible: str = ", ".join(sorted(constants)) or "none"
        raise CompileInputError(
            f"Unknown constant '{name}'{scope_help} in '{file_path}'. Visible constants: {visible}",
        )
    return render_constant_declaration(
        declaration=declaration,
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
        file_path=file_path,
    )


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


def _inaccessible_declaration_message(
    *, kind: str, name: str, record: DeclarationRecord, consumer: Path
) -> str:
    owner: str = record.owning_path or record.ownership_root.path
    owner_identity: str = (
        f" ({record.identity.owner.kind.value} '{record.identity.owner.name}')"
        if record.identity.owner is not None
        else ""
    )
    return (
        f"{kind.capitalize()} '{name}' is known but inaccessible in '{consumer}'. "
        f"It is defined at {record.path}:{record.line}:{record.column} with "
        f"{record.scope.value} scope owned by '{owner}'{owner_identity}; "
        f"consumer path: '{consumer}'"
    )


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
