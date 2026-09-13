"""Expected-model declaration grants with tolerant relationship faults."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.macros import find_macro_call_names
from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_expected_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    extract_sql_test_ctes,
    extract_sql_test_expected_model_names,
)
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestCtes,
    CompileSqlTestCtes,
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
    ScopeIndex,
    ScopeLookup,
    VisibilityResolution,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, GrantKind, ResourceKind, ScopeKind


def build_scope_relationship_grants(
    *, discovered_inputs: DiscoveredProjectInputs, index: ScopeIndex
) -> ScopeRelationshipBuild:
    """Return expected-model grants while retaining independent extraction faults."""

    lookup: ScopeLookup = build_scope_lookup(index=index)
    test_grants, test_faults = _test_relationship_grants(
        discovered_inputs=discovered_inputs, lookup=lookup
    )
    scenario_grants, scenario_faults = _scenario_relationship_grants(
        discovered_inputs=discovered_inputs, lookup=lookup
    )
    return ScopeRelationshipBuild(
        grants=tuple(dict.fromkeys((*test_grants, *scenario_grants))),
        faults=(*test_faults, *scenario_faults),
    )


def _test_relationship_grants(
    *, discovered_inputs: DiscoveredProjectInputs, lookup: ScopeLookup
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
                        include_macros=True,
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
    *, discovered_inputs: DiscoveredProjectInputs, lookup: ScopeLookup
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
    include_macros: bool = False,
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
            if declaration.scope is ScopeKind.PRIVATE or (
                declaration.identity.kind is DeclarationKind.MACRO and not include_macros
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


def _tested_macro_grants(
    *, lookup: ScopeLookup, resource: ResourceIdentity, sql: str, file_label: str
) -> list[GrantRecord]:
    test_ctes: CompileSqlTestCtes = extract_sql_test_ctes(
        sql=sql, file_label=file_label, mode=SqlTestMode.MACRO
    )
    if not isinstance(test_ctes.payload, CompileDirectLogicSqlTestCtes):
        return []
    tested_macro_names: tuple[str, ...] = find_macro_call_names(
        test_ctes.payload.actual_cte.sql_body
    )
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
