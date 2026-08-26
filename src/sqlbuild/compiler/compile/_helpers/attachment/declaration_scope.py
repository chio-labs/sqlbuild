"""Build process-local declaration scope state for one compile invocation."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_declaration_scope_resolver,
)
from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_expected_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_sql_test_expected_model_names,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import DeclarationScopeBuild, LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.main._build_scope_index import build_scope_index
from sqlbuild.compiler.scopes.main._build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main._resolve_scope_visibility import resolve_scope_visibility
from sqlbuild.compiler.scopes.main._validate_scope_index import validate_scope_index
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    GrantRecord,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, ScopeKind


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

    lookup: ScopeLookup = build_scope_lookup(index=build.index)
    grants: list[GrantRecord] = []
    for test_file in discovered_inputs.test_files:
        for block in test_file.blocks:
            resource: ResourceIdentity = ResourceIdentity(
                ResourceKind.TEST, block.name or test_file.relative_path.stem
            )
            expected_model_names: tuple[str, ...] = extract_sql_test_expected_model_names(
                sql=block.sql_body,
                file_label=str(test_file.relative_path),
                mode=block.mode,
            )
            grants.extend(
                _expected_model_grants(
                    lookup=lookup,
                    resource=resource,
                    expected_model_names=expected_model_names,
                )
            )
    for scenario_file in discovered_inputs.scenario_files:
        resource: ResourceIdentity = ResourceIdentity(ResourceKind.SCENARIO, scenario_file.name)
        expected_model_names: tuple[str, ...] = extract_sql_scenario_expected_model_names(
            sql=scenario_file.sql_body,
            file_label=str(scenario_file.relative_path),
        )
        grants.extend(
            _expected_model_grants(
                lookup=lookup,
                resource=resource,
                expected_model_names=expected_model_names,
            )
        )

    index: ScopeIndex = replace(
        build.index,
        grants=tuple(dict.fromkeys((*build.index.grants, *grants))),
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


def _expected_model_grants(
    *,
    lookup: ScopeLookup,
    resource: ResourceIdentity,
    expected_model_names: tuple[str, ...],
) -> list[GrantRecord]:
    grants: list[GrantRecord] = []
    for model_name in expected_model_names:
        through: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, model_name)
        resolution: VisibilityResolution = resolve_scope_visibility(lookup=lookup, target=through)
        for visible in resolution.visible:
            records: tuple[DeclarationRecord, ...] = lookup.declarations.get(
                visible.declaration, ()
            )
            if not records:
                continue
            declaration: DeclarationRecord = records[0]
            if declaration.scope is ScopeKind.PRIVATE or declaration.identity.kind not in {
                DeclarationKind.ENUM,
                DeclarationKind.CONSTANT,
            }:
                continue
            grants.append(
                GrantRecord(
                    resource=resource,
                    declaration=declaration.identity,
                    through=through,
                )
            )
    return grants
