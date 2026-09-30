"""Build process-local declaration scope state for one compile invocation."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import CodeType

from sqlbuild.compiler.compile._helpers.attachment.scope_relationships import (
    build_scope_relationship_grants,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_declaration_scope_resolver,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationScopeBuild,
    LoadedMacro,
    ScopeRelationshipBuild,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.main._build_scope_index import build_scope_index
from sqlbuild.compiler.scopes.main._validate_scope_index import validate_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind


def build_declaration_scope(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
    compile_cache_dir: Path | None = None,
) -> DeclarationScopeBuild:
    """Build one canonical index and validate it before SQL expansion."""

    index: ScopeIndex = build_scope_index(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
    )
    try:
        validate_scope_index(index=index)
    except ScopeValidationError as error:
        raise CompileInputError(str(error)) from error
    has_scoped_relationship_declarations: bool = any(
        declaration.scope is not ScopeKind.GLOBAL
        and declaration.identity.kind
        in {DeclarationKind.ENUM, DeclarationKind.CONSTANT, DeclarationKind.MACRO}
        for declaration in index.declarations
    )
    relationships: ScopeRelationshipBuild = (
        build_scope_relationship_grants(
            discovered_inputs=discovered_inputs,
            index=index,
            compile_cache_dir=compile_cache_dir,
        )
        if has_scoped_relationship_declarations
        and (discovered_inputs.test_files or discovered_inputs.scenario_files)
        else ScopeRelationshipBuild()
    )
    if relationships.faults:
        raise CompileInputError(relationships.faults[0].message)
    index = replace(
        index,
        grants=tuple(dict.fromkeys((*index.grants, *relationships.grants))),
        completeness=replace(index.completeness, relationships=True),
    )
    return DeclarationScopeBuild(
        loaded_macros=loaded_macros,
        index=index,
        resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=index,
            loaded_macros=loaded_macros,
        ),
    )


def rebind_declaration_scope(
    *,
    scope: DeclarationScopeBuild,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
) -> DeclarationScopeBuild | None:
    """Pair a built index with private macro instances, or return None if their metadata differs."""

    if _indexed_macro_metadata(loaded_macros) != _indexed_macro_metadata(scope.loaded_macros):
        return None
    return DeclarationScopeBuild(
        loaded_macros=loaded_macros,
        index=scope.index,
        resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=scope.index,
            loaded_macros=loaded_macros,
        ),
    )


def _indexed_macro_metadata(loaded_macros: Mapping[str, LoadedMacro]) -> tuple[object, ...]:
    return tuple(
        (
            key,
            macro.name,
            macro.relative_path,
            macro.raw_source,
            macro.dependencies,
            code.co_firstlineno
            if isinstance(code := getattr(macro.function, "__code__", None), CodeType)
            else None,
            tuple(inspect.signature(macro.function).parameters),
        )
        for key, macro in loaded_macros.items()
    )
