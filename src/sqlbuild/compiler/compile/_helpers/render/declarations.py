"""Compile-time resolution for enum and constant declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from sqlbuild.compiler.compile.constants import MACRO_TOKEN, SQL_QUOTE_TOKENS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationExpansionContext,
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
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.scopes.main._build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main._resolve_scope_path_visibility import (
    resolve_scope_path_visibility,
)
from sqlbuild.compiler.scopes.main._resolve_scope_visibility import resolve_scope_visibility
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    ScopeIndex,
    UsageRecord,
    VisibilityRecord,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, UsageKind
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
_CONTEXT: str = "Enum and constant expansion"
_ACCEPTED_VALUES_AUDIT: str = "accepted_values"
_ENUM_REFERENCE_KIND: str = "enum"


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
    return DeclarationScopeResolver(
        project_dir=discovered_inputs.project_dir,
        lookup=build_scope_lookup(index=scope_index),
        projection=DeclarationRuntimeProjection(declarations=MappingProxyType(declarations)),
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
    resolution: VisibilityResolution = resolve_scope_visibility(
        lookup=resolver.lookup, target=resource or target_path
    )
    enums: dict[str, EnumDeclaration] = {}
    constants: dict[str, ConstantDeclaration] = {}
    inaccessible_enums: dict[str, DeclarationRecord] = {}
    inaccessible_constants: dict[str, DeclarationRecord] = {}
    macros: dict[str, LoadedMacro] = {}
    macro_records: dict[str, DeclarationRecord] = {}
    inaccessible_macros: dict[str, DeclarationRecord] = {}
    visibility_by_declaration: dict[DeclarationIdentity, list[VisibilityRecord]] = {}
    if resolution.target.unknown:
        lexical_target_path: Path = target_path
        definition_record: DeclarationRecord | None = next(
            (
                record
                for record in resolver.lookup.index.declarations
                if record.path == target_path.as_posix()
                and record.identity.kind is DeclarationKind.MACRO
            ),
            None,
        )
        if definition_record is not None:
            lexical_target_path = Path(definition_record.owning_path or ".") / "__macro__.sql"
        visible_records, inaccessible_records = resolve_scope_path_visibility(
            lookup=resolver.lookup, path=lexical_target_path
        )
    else:
        visible_records: tuple[DeclarationRecord, ...] = tuple(
            resolver.lookup.declarations[item.declaration][0] for item in resolution.visible
        )
        inaccessible_records: tuple[DeclarationRecord, ...] = tuple(
            resolver.lookup.declarations[item.declaration][0] for item in resolution.inaccessible
        )
        for visible_record in resolution.visible:
            visibility_by_declaration.setdefault(visible_record.declaration, []).append(
                visible_record
            )
    for visible in visible_records:
        value: EnumDeclaration | ConstantDeclaration | LoadedMacro | None = (
            resolver.projection.declarations.get(visible.identity)
        )
        if isinstance(value, EnumDeclaration):
            enums[visible.identity.name] = value
        elif isinstance(value, ConstantDeclaration):
            constants[visible.identity.name] = value
        elif isinstance(value, LoadedMacro):
            macros[visible.identity.name] = value
            macro_records[visible.identity.name] = visible
    for record in inaccessible_records:
        if record.identity.kind is DeclarationKind.ENUM:
            inaccessible_enums[record.identity.name] = record
        elif record.identity.kind is DeclarationKind.CONSTANT:
            inaccessible_constants[record.identity.name] = record
        elif record.identity.kind is DeclarationKind.MACRO:
            inaccessible_macros[record.identity.name] = record
    enum_visibility: dict[str, tuple[VisibilityRecord, ...]] = {}
    constant_visibility: dict[str, tuple[VisibilityRecord, ...]] = {}
    for record in visible_records:
        records: tuple[VisibilityRecord, ...] = tuple(
            visibility_by_declaration.get(record.identity, ())
        )
        if record.identity.kind is DeclarationKind.ENUM:
            enum_visibility[record.identity.name] = records
        elif record.identity.kind is DeclarationKind.CONSTANT:
            constant_visibility[record.identity.name] = records
    return DeclarationResolutionContext(
        enums=enums,
        constants=constants,
        inaccessible_enums=inaccessible_enums,
        inaccessible_constants=inaccessible_constants,
        enum_visibility=enum_visibility,
        constant_visibility=constant_visibility,
        macros=macros,
        macro_records=macro_records,
        inaccessible_macros=inaccessible_macros,
    )


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
        for record in visibility:
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

    if context.resolver is None:
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


def expand_declaration_references(
    *,
    sql: str,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    constants: dict[str, ConstantDeclaration],
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
    inaccessible_enums: dict[str, DeclarationRecord] | None = None,
    inaccessible_constants: dict[str, DeclarationRecord] | None = None,
) -> str:
    """Resolve enum-member and constant references to SQL scalar literals."""

    rendered_sql: str
    rendered_sql, _spans = expand_declaration_references_with_spans(
        sql=sql,
        file_path=file_path,
        enums=enums,
        constants=constants,
        value_renderer=value_renderer,
        collection_rendering=collection_rendering,
        inaccessible_enums=inaccessible_enums,
        inaccessible_constants=inaccessible_constants,
    )
    return rendered_sql


def expand_declaration_references_with_spans(
    *,
    sql: str,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    constants: dict[str, ConstantDeclaration],
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
    inaccessible_enums: dict[str, DeclarationRecord] | None = None,
    inaccessible_constants: dict[str, DeclarationRecord] | None = None,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Resolve declaration references, returning the span of every substitution."""

    rendered_parts: list[str] = []
    spans: list[ExpansionSpan] = []
    output_length: int = 0
    cursor: int = 0
    while cursor < len(sql):
        reference_start: int | None = _find_next_reference_start(sql=sql, start=cursor)
        if reference_start is None:
            rendered_parts.append(sql[cursor:])
            break
        leading_literal: str = sql[cursor:reference_start]
        rendered_parts.append(leading_literal)
        output_length += len(leading_literal)
        start_match: re.Match[str] | None = _DECLARATION_REFERENCE_START_PATTERN.match(
            sql, reference_start
        )
        if start_match is None:
            raise CompileInputError(f"Invalid declaration reference in '{file_path}'")
        kind: str = start_match.group("kind")
        if kind == _ENUM_REFERENCE_KIND:
            replacement: str
            next_cursor: int
            replacement, next_cursor = _resolve_enum_reference(
                sql=sql,
                reference_start=reference_start,
                file_path=file_path,
                enums=enums,
                inaccessible_enums=inaccessible_enums or {},
            )
        else:
            replacement, next_cursor = _resolve_constant_reference(
                sql=sql,
                reference_start=reference_start,
                file_path=file_path,
                constants=constants,
                inaccessible_constants=inaccessible_constants or {},
                value_renderer=value_renderer,
                collection_rendering=collection_rendering,
            )
        rendered_parts.append(replacement)
        spans.append(
            ExpansionSpan(
                source_start=reference_start,
                source_end=next_cursor,
                output_start=output_length,
                output_end=output_length + len(replacement),
            )
        )
        output_length += len(replacement)
        cursor = next_cursor
    return "".join(rendered_parts), tuple(spans)


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


def _resolve_enum_reference(
    *,
    sql: str,
    reference_start: int,
    file_path: Path,
    enums: dict[str, EnumDeclaration],
    inaccessible_enums: dict[str, DeclarationRecord],
) -> tuple[str, int]:
    match: re.Match[str] | None = _ENUM_REFERENCE_PATTERN.match(sql, reference_start)
    if match is None:
        raise CompileInputError(
            f"Invalid enum reference in '{file_path}'; use @enum(\"name\").MEMBER"
        )
    name: str = match.group("name")
    declaration: EnumDeclaration | None = enums.get(name)
    if declaration is None:
        inaccessible: DeclarationRecord | None = inaccessible_enums.get(name)
        if inaccessible is not None:
            raise CompileInputError(
                _inaccessible_declaration_message(
                    kind="enum", name=name, record=inaccessible, consumer=file_path
                )
            )
        scope_help: str = " in this model" if name.startswith("_") else ""
        visible: str = ", ".join(sorted(enums)) or "none"
        raise CompileInputError(
            f"Unknown enum '{name}'{scope_help} in '{file_path}'. Visible enums: {visible}"
        )
    member_name: str = match.group("member")
    member: EnumMember | None = next(
        (candidate for candidate in declaration.members if candidate.name == member_name),
        None,
    )
    if member is None:
        available: str = ", ".join(item.name for item in declaration.members)
        raise CompileInputError(
            f"Unknown member '{member_name}' for enum '{name}' in '{file_path}'. "
            f"Available members: {available}"
        )
    return _render_scalar(value=member.value), match.end()


def _resolve_constant_reference(
    *,
    sql: str,
    reference_start: int,
    file_path: Path,
    constants: dict[str, ConstantDeclaration],
    inaccessible_constants: dict[str, DeclarationRecord],
    value_renderer: TypedSqlValueRenderer,
    collection_rendering: CollectionRendering,
) -> tuple[str, int]:
    match: re.Match[str] | None = _CONSTANT_REFERENCE_PATTERN.match(sql, reference_start)
    if match is None:
        raise CompileInputError(
            f"Invalid constant reference in '{file_path}'; use @const(\"name\")"
        )
    name: str = match.group("name")
    declaration: ConstantDeclaration | None = constants.get(name)
    if declaration is None:
        inaccessible: DeclarationRecord | None = inaccessible_constants.get(name)
        if inaccessible is not None:
            raise CompileInputError(
                _inaccessible_declaration_message(
                    kind="constant", name=name, record=inaccessible, consumer=file_path
                )
            )
        scope_help: str = " in this model" if name.startswith("_") else ""
        visible: str = ", ".join(sorted(constants)) or "none"
        raise CompileInputError(
            f"Unknown constant '{name}'{scope_help} in '{file_path}'. Visible constants: {visible}"
        )
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
            f"in '{file_path}' by adapter '{value_renderer.adapter_name}' as "
            f"{selected_rendering.value}: {error}"
        ) from error
    return rendered, match.end()


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


def _render_scalar(*, value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"


def _find_next_reference_start(*, sql: str, start: int) -> int | None:
    if MACRO_TOKEN not in sql[start:]:
        return None
    index: int = start
    while index < len(sql):
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
