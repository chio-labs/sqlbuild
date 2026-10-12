"""Compile-time resolution for enum and constant declarations."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from types import MappingProxyType

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
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
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
)
from sqlbuild.compiler.model_loop.main._build_native_declaration_contexts import (
    build_native_declaration_contexts,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    ScopeKind,
)
from sqlbuild.sql_values.exceptions import SqlValueRenderingError, SqlValueValidationError
from sqlbuild.sql_values.main.validate_rendered_size import validate_rendered_sql_value_size
from sqlbuild.sql_values.types import CollectionRendering, SqlValueKind

_ACCEPTED_VALUES_AUDIT: str = "accepted_values"


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
    context, _ = resolver.native_contexts.resolve(resolver, file_path, resource)
    return context


def build_model_declaration_indexes(
    *, model_file: DiscoveredSqlModelFile
) -> tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]]:
    """Build collision-checked declaration indexes private to one model."""

    return (
        {declaration.name: declaration for declaration in model_file.enum_declarations},
        {declaration.name: declaration for declaration in model_file.constant_declarations},
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
