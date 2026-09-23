"""Expected-model declaration grants with tolerant relationship faults."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.macros import (
    find_macro_call_names,
    find_nested_macro_call_names,
)
from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_expected_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_sql_test_expected_model_names,
    extract_unclassified_sql_test_ctes,
)
from sqlbuild.compiler.compile.constants import MACRO_ACTUAL_TEST_CTE_NAME
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
    ScopeRelationshipBuild,
    ScopeRelationshipFault,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.main._resolve_scope_path_visibility import (
    resolve_scope_path_visibility,
)
from sqlbuild.compiler.scopes.main._resolve_scope_visibility import resolve_scope_visibility
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    GrantRecord,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    ScopeLookup,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, GrantKind, ResourceKind, ScopeKind

type _SharedDeclarations = dict[tuple[str, str], tuple[DeclarationRecord, ...]]


def build_scope_relationship_grants(
    *, discovered_inputs: DiscoveredProjectInputs, index: ScopeIndex
) -> ScopeRelationshipBuild:
    """Return expected-model grants while retaining independent extraction faults."""

    lookup: ScopeLookup = build_scope_lookup(index=index)
    shared_declarations: _SharedDeclarations = _shared_declarations_by_directory(lookup=lookup)
    test_grants, test_faults = _test_relationship_grants(
        discovered_inputs=discovered_inputs,
        lookup=lookup,
        shared_declarations=shared_declarations,
    )
    scenario_grants, scenario_faults = _scenario_relationship_grants(
        discovered_inputs=discovered_inputs,
        lookup=lookup,
        shared_declarations=shared_declarations,
    )
    return ScopeRelationshipBuild(
        grants=tuple(dict.fromkeys((*test_grants, *scenario_grants))),
        faults=(*test_faults, *scenario_faults),
    )


def _test_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    lookup: ScopeLookup,
    shared_declarations: _SharedDeclarations,
) -> tuple[tuple[GrantRecord, ...], tuple[ScopeRelationshipFault, ...]]:
    grants: list[GrantRecord] = []
    faults: list[ScopeRelationshipFault] = []
    for test_file in discovered_inputs.test_files:
        for block in test_file.blocks:
            try:
                expected_names: tuple[str, ...] = extract_sql_test_expected_model_names(
                    sql=block.sql_body,
                    file_label=str(test_file.relative_path),
                    mode=block.mode,
                )
                grants.extend(
                    _expected_model_grants(
                        lookup=lookup,
                        resource=ResourceIdentity(
                            ResourceKind.TEST, block.name or test_file.relative_path.stem
                        ),
                        expected_model_names=expected_names,
                        shared_declarations=shared_declarations,
                        called_macros=frozenset(find_nested_macro_call_names(block.sql_body)),
                    )
                )
                if block.mode is SqlTestMode.MACRO:
                    grants.extend(
                        _tested_macro_grants(
                            lookup=lookup,
                            resource=ResourceIdentity(
                                ResourceKind.TEST, block.name or test_file.relative_path.stem
                            ),
                            sql=block.sql_body,
                            file_label=str(test_file.relative_path),
                        )
                    )
            except Exception as error:
                faults.append(ScopeRelationshipFault(test_file.relative_path, str(error)))
    return tuple(grants), tuple(faults)


def _scenario_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    lookup: ScopeLookup,
    shared_declarations: _SharedDeclarations,
) -> tuple[tuple[GrantRecord, ...], tuple[ScopeRelationshipFault, ...]]:
    grants: list[GrantRecord] = []
    faults: list[ScopeRelationshipFault] = []
    for scenario in discovered_inputs.scenario_files:
        try:
            expected_names: tuple[str, ...] = extract_sql_scenario_expected_model_names(
                sql=scenario.sql_body, file_label=str(scenario.relative_path)
            )
            grants.extend(
                _expected_model_grants(
                    lookup=lookup,
                    resource=ResourceIdentity(ResourceKind.SCENARIO, scenario.name),
                    expected_model_names=expected_names,
                    shared_declarations=shared_declarations,
                )
            )
        except Exception as error:
            faults.append(ScopeRelationshipFault(scenario.relative_path, str(error)))
    return tuple(grants), tuple(faults)


def _expected_model_grants(
    *,
    lookup: ScopeLookup,
    resource: ResourceIdentity,
    expected_model_names: tuple[str, ...],
    shared_declarations: _SharedDeclarations,
    called_macros: frozenset[str] = frozenset(),
) -> list[GrantRecord]:
    grants: list[GrantRecord] = []
    for model_name in expected_model_names:
        through: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, model_name)
        for declaration in _shared_visible_declarations(
            lookup=lookup, resource=through, shared=shared_declarations
        ):
            if (
                declaration.identity.kind is DeclarationKind.MACRO
                and declaration.identity.name not in called_macros
            ):
                continue
            grants.append(
                GrantRecord(
                    resource=resource,
                    declaration=declaration.identity,
                    through=through,
                )
            )
    return grants


def _shared_declarations_by_directory(*, lookup: ScopeLookup) -> _SharedDeclarations:
    """Resolve shared non-private visibility once per model directory and ownership root."""

    representatives: dict[tuple[str, str], ResourceIdentity] = {}
    for identity, records in lookup.resources.items():
        if (
            identity.kind is ResourceKind.MODEL
            and len(records) == 1
            and identity not in lookup.grants_by_resource
        ):
            representatives.setdefault(_directory_key(record=records[0]), identity)
    return {
        key: _resolve_shared_declarations(lookup=lookup, resource=identity)
        for key, identity in representatives.items()
    }


def _directory_key(*, record: ResourceRecord) -> tuple[str, str]:
    return (Path(record.path).parent.as_posix(), record.ownership_root.path)


def _shared_visible_declarations(
    *, lookup: ScopeLookup, resource: ResourceIdentity, shared: _SharedDeclarations
) -> tuple[DeclarationRecord, ...]:
    """Return non-private declarations a resource sees, reusing its directory's resolution."""

    records: tuple[ResourceRecord, ...] = lookup.resources.get(resource, ())
    if len(records) == 1 and resource not in lookup.grants_by_resource:
        directory_declarations: tuple[DeclarationRecord, ...] | None = shared.get(
            _directory_key(record=records[0])
        )
        if directory_declarations is not None:
            return directory_declarations
    return _resolve_shared_declarations(lookup=lookup, resource=resource)


def _resolve_shared_declarations(
    *, lookup: ScopeLookup, resource: ResourceIdentity
) -> tuple[DeclarationRecord, ...]:
    resolution: VisibilityResolution = resolve_scope_visibility(lookup=lookup, target=resource)
    declarations: list[DeclarationRecord] = []
    for visible in resolution.visible:
        records: tuple[DeclarationRecord, ...] = lookup.declarations.get(visible.declaration, ())
        if records and records[0].scope is not ScopeKind.PRIVATE:
            declarations.append(records[0])
    return tuple(declarations)


def _tested_macro_grants(
    *, lookup: ScopeLookup, resource: ResourceIdentity, sql: str, file_label: str
) -> list[GrantRecord]:
    test_ctes: tuple[CompileSqlTestCte, ...] = extract_unclassified_sql_test_ctes(
        sql=sql, file_label=file_label
    )
    actual_cte: CompileSqlTestCte | None = next(
        (cte for cte in test_ctes if cte.name == MACRO_ACTUAL_TEST_CTE_NAME), None
    )
    if actual_cte is None:
        return []
    tested_macro_names: tuple[str, ...] = find_macro_call_names(actual_cte.sql_body)
    direct_resolution: VisibilityResolution = resolve_scope_visibility(
        lookup=lookup, target=resource
    )
    directly_visible: frozenset[DeclarationIdentity] = frozenset(
        visible.declaration for visible in direct_resolution.visible
    )
    grants: list[GrantRecord] = []
    for macro_name in tested_macro_names:
        records: tuple[DeclarationRecord, ...] = lookup.declarations.get(
            DeclarationIdentity(DeclarationKind.MACRO, macro_name), ()
        )
        if not records:
            continue
        tested_macro: DeclarationRecord = records[0]
        lexical_path: Path = Path(tested_macro.owning_path or ".") / "__macro_test__.sql"
        visible, _inaccessible = resolve_scope_path_visibility(lookup=lookup, path=lexical_path)
        for declaration in visible:
            if declaration.scope is ScopeKind.PRIVATE or declaration.identity in directly_visible:
                continue
            grants.append(
                GrantRecord(
                    resource=resource,
                    declaration=declaration.identity,
                    through=tested_macro.identity,
                    kind=GrantKind.TESTED_MACRO,
                )
            )
    return grants
