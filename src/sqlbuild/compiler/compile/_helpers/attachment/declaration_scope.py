"""Build process-local declaration scope state for one compile invocation."""

from __future__ import annotations

from dataclasses import replace

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


def build_declaration_scope(
    *, discovered_inputs: DiscoveredProjectInputs, loaded_macros: dict[str, LoadedMacro]
) -> DeclarationScopeBuild:
    """Build one canonical index and validate it before SQL expansion."""

    index: ScopeIndex = build_scope_index(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
    )
    try:
        validate_scope_index(index=index)
    except ScopeValidationError as error:
        raise CompileInputError(str(error)) from error
    build: DeclarationScopeBuild = DeclarationScopeBuild(
        loaded_macros=loaded_macros,
        index=index,
        resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=index,
            loaded_macros=loaded_macros,
        ),
    )
    return attach_expected_model_grants(
        build=build,
        discovered_inputs=discovered_inputs,
    )


def attach_expected_model_grants(
    *, build: DeclarationScopeBuild, discovered_inputs: DiscoveredProjectInputs
) -> DeclarationScopeBuild:
    """Return scope state enriched by explicit test and scenario model relationships."""

    relationships: ScopeRelationshipBuild = build_scope_relationship_grants(
        discovered_inputs=discovered_inputs, index=build.index
    )
    if relationships.faults:
        raise CompileInputError(relationships.faults[0].message)

    index: ScopeIndex = replace(
        build.index,
        grants=tuple(dict.fromkeys((*build.index.grants, *relationships.grants))),
        completeness=replace(build.index.completeness, relationships=True),
    )
    return replace(
        build,
        index=index,
        resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=index,
            loaded_macros=build.loaded_macros,
        ),
    )
