"""Expected-model declaration grants with tolerant relationship faults."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

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
from sqlbuild.compiler.compile.constants import (
    MACRO_ACTUAL_TEST_CTE_NAME,
    SQL_TEST_EXPECTED_MODELS_FACT_ALGORITHM,
    SQL_TEST_FACT_CACHE_NAMESPACE,
)
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
    ScopeRelationshipBuild,
    ScopeRelationshipFault,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlTestFile
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore
from sqlbuild.compiler.scopes.main._native_expected_model_names import (
    native_expected_model_names,
)
from sqlbuild.compiler.scopes.main._resolve_scope_declaration_visibility import (
    resolve_scope_declaration_visibility,
)
from sqlbuild.compiler.scopes.main._resolve_scope_path_visibility import (
    resolve_scope_path_visibility,
)
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationVisibility,
    GrantRecord,
    RelationshipFact,
    ResourceIdentity,
    ResourceRecord,
    ScopeIndex,
    ScopeLookup,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, GrantKind, ResourceKind, ScopeKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

type _SharedDeclarations = dict[tuple[str, str], tuple[DeclarationRecord, ...]]


def build_scope_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    index: ScopeIndex,
    sql_lexical_syntax: SqlLexicalSyntax,
    compile_cache_dir: Path | None = None,
) -> ScopeRelationshipBuild:
    """Return expected-model grants while retaining independent extraction faults."""

    lookup: ScopeLookup = build_scope_lookup(index=index)
    shared_declarations: _SharedDeclarations = _shared_declarations_by_directory(lookup=lookup)
    with FactCacheStore(
        root=compile_cache_dir,
        namespace=SQL_TEST_FACT_CACHE_NAMESPACE,
        algorithm=SQL_TEST_EXPECTED_MODELS_FACT_ALGORITHM,
    ) as fact_cache:
        test_grants, test_faults = _test_relationship_grants(
            discovered_inputs=discovered_inputs,
            lookup=lookup,
            shared_declarations=shared_declarations,
            fact_cache=fact_cache,
            syntax=sql_lexical_syntax,
        )
    scenario_grants, scenario_faults = _scenario_relationship_grants(
        discovered_inputs=discovered_inputs,
        lookup=lookup,
        shared_declarations=shared_declarations,
        syntax=sql_lexical_syntax,
    )
    return ScopeRelationshipBuild(
        grants=tuple(dict.fromkeys((*test_grants, *scenario_grants))),
        faults=(*test_faults, *scenario_faults),
    )


def extract_scope_relationship_facts(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    sql_lexical_syntax: SqlLexicalSyntax,
    compile_cache_dir: Path | None = None,
) -> tuple[tuple[RelationshipFact, ...], str | None]:
    """Return the relationship names grants are resolved from, and the first extraction fault."""

    facts: list[RelationshipFact] = []
    faults: list[ScopeRelationshipFault] = []
    with FactCacheStore(
        root=compile_cache_dir,
        namespace=SQL_TEST_FACT_CACHE_NAMESPACE,
        algorithm=SQL_TEST_EXPECTED_MODELS_FACT_ALGORITHM,
    ) as fact_cache:
        cache_keys: dict[int, str] = (
            {
                file_index: _expected_models_fact_key(
                    test_file=test_file, fact_cache=fact_cache, syntax=sql_lexical_syntax
                )
                for file_index, test_file in enumerate(discovered_inputs.test_files)
            }
            if fact_cache.enabled
            else {}
        )
        cached_names: dict[str, object] = fact_cache.read_many(
            tuple(
                (_expected_models_fact_slot(discovered_inputs.test_files[file_index]), cache_key)
                for file_index, cache_key in cache_keys.items()
            )
        )
        cached_by_file: list[tuple[tuple[str, ...], ...] | None] = [
            _cached_expected_names(
                value=cached_names.get(cache_keys[file_index])
                if file_index in cache_keys
                else None,
                block_count=len(test_file.blocks),
            )
            for file_index, test_file in enumerate(discovered_inputs.test_files)
        ]
        scanned_names: dict[tuple[int, int], tuple[str, ...]] = _scanned_expected_names(
            test_files=discovered_inputs.test_files,
            cached_by_file=cached_by_file,
            syntax=sql_lexical_syntax,
        )
        for file_index, test_file in enumerate(discovered_inputs.test_files):
            cache_key: str | None = cache_keys.get(file_index)
            cached_file_names: tuple[tuple[str, ...], ...] | None = cached_by_file[file_index]
            extracted_names: list[tuple[str, ...]] = []
            for block_index, block in enumerate(test_file.blocks):
                scanned: tuple[str, ...] | None = scanned_names.get((file_index, block_index))
                try:
                    expected_names: tuple[str, ...] = (
                        cached_file_names[block_index]
                        if cached_file_names is not None
                        else scanned
                        if scanned is not None
                        else extract_sql_test_expected_model_names(
                            sql=block.sql_body,
                            file_label=str(test_file.relative_path),
                            syntax=sql_lexical_syntax,
                            mode=block.mode,
                        )
                    )
                    extracted_names.append(expected_names)
                    called_macros: tuple[str, ...] = find_nested_macro_call_names(block.sql_body)
                    facts.append(
                        RelationshipFact(
                            resource=ResourceIdentity(
                                ResourceKind.TEST, block.name or test_file.relative_path.stem
                            ),
                            expected_models=expected_names,
                            called_macros=called_macros,
                            tested_macros=(
                                _tested_macro_names(
                                    sql=block.sql_body,
                                    file_label=str(test_file.relative_path),
                                    syntax=sql_lexical_syntax,
                                )
                                if block.mode is SqlTestMode.MACRO
                                else ()
                            ),
                        )
                    )
                except Exception as error:
                    faults.append(ScopeRelationshipFault(test_file.relative_path, str(error)))
            if (
                cache_key is not None
                and cached_file_names is None
                and len(extracted_names) == len(test_file.blocks)
            ):
                fact_cache.stage(
                    key=cache_key,
                    slot=_expected_models_fact_slot(test_file),
                    value=tuple(extracted_names),
                )
    scenario_names: list[tuple[str, ...] | None] = native_expected_model_names(
        sqls=[scenario.sql_body for scenario in discovered_inputs.scenario_files],
        syntax=sql_lexical_syntax,
    )
    for scenario, scanned in zip(discovered_inputs.scenario_files, scenario_names, strict=True):
        try:
            facts.append(
                RelationshipFact(
                    resource=ResourceIdentity(ResourceKind.SCENARIO, scenario.name),
                    expected_models=scanned
                    if scanned is not None
                    else extract_sql_scenario_expected_model_names(
                        sql=scenario.sql_body,
                        file_label=str(scenario.relative_path),
                        syntax=sql_lexical_syntax,
                    ),
                )
            )
        except Exception as error:
            faults.append(ScopeRelationshipFault(scenario.relative_path, str(error)))
    return tuple(facts), faults[0].message if faults else None


def _scanned_expected_names(
    *,
    test_files: Sequence[DiscoveredSqlTestFile],
    cached_by_file: Sequence[tuple[tuple[str, ...], ...] | None],
    syntax: SqlLexicalSyntax,
) -> dict[tuple[int, int], tuple[str, ...]]:
    """Scan uncached model-mode blocks natively, keeping only the names the scan reproduces."""

    pending: list[tuple[int, int]] = []
    for file_index, test_file in enumerate(test_files):
        if cached_by_file[file_index] is not None:
            continue
        pending.extend(
            (file_index, block_index)
            for block_index, block in enumerate(test_file.blocks)
            if block.mode is SqlTestMode.MODEL
        )
    scanned: list[tuple[str, ...] | None] = native_expected_model_names(
        sqls=[
            test_files[file_index].blocks[block_index].sql_body
            for file_index, block_index in pending
        ],
        syntax=syntax,
    )
    return {
        position: names
        for position, names in zip(pending, scanned, strict=True)
        if names is not None
    }


def _tested_macro_names(*, sql: str, file_label: str, syntax: SqlLexicalSyntax) -> tuple[str, ...]:
    test_ctes: tuple[CompileSqlTestCte, ...] = extract_unclassified_sql_test_ctes(
        sql=sql, file_label=file_label, syntax=syntax
    )
    actual_cte: CompileSqlTestCte | None = next(
        (cte for cte in test_ctes if cte.name == MACRO_ACTUAL_TEST_CTE_NAME), None
    )
    return () if actual_cte is None else find_macro_call_names(actual_cte.sql_body)


def _test_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    lookup: ScopeLookup,
    shared_declarations: _SharedDeclarations,
    fact_cache: FactCacheStore,
    syntax: SqlLexicalSyntax,
) -> tuple[tuple[GrantRecord, ...], tuple[ScopeRelationshipFault, ...]]:
    grants: list[GrantRecord] = []
    faults: list[ScopeRelationshipFault] = []
    cache_keys: dict[int, str] = (
        {
            file_index: _expected_models_fact_key(
                test_file=test_file, fact_cache=fact_cache, syntax=syntax
            )
            for file_index, test_file in enumerate(discovered_inputs.test_files)
        }
        if fact_cache.enabled
        else {}
    )
    cached_names: dict[str, object] = fact_cache.read_many(
        tuple(
            (_expected_models_fact_slot(discovered_inputs.test_files[file_index]), cache_key)
            for file_index, cache_key in cache_keys.items()
        )
    )
    for file_index, test_file in enumerate(discovered_inputs.test_files):
        cache_key: str | None = cache_keys.get(file_index)
        cached_file_names: tuple[tuple[str, ...], ...] | None = _cached_expected_names(
            value=None if cache_key is None else cached_names.get(cache_key),
            block_count=len(test_file.blocks),
        )
        extracted_names: list[tuple[str, ...]] = []
        for block_index, block in enumerate(test_file.blocks):
            try:
                expected_names: tuple[str, ...] = (
                    cached_file_names[block_index]
                    if cached_file_names is not None
                    else extract_sql_test_expected_model_names(
                        sql=block.sql_body,
                        file_label=str(test_file.relative_path),
                        syntax=syntax,
                        mode=block.mode,
                    )
                )
                extracted_names.append(expected_names)
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
                            syntax=syntax,
                        )
                    )
            except Exception as error:
                faults.append(ScopeRelationshipFault(test_file.relative_path, str(error)))
        if (
            cache_key is not None
            and cached_file_names is None
            and len(extracted_names) == len(test_file.blocks)
        ):
            fact_cache.stage(
                key=cache_key,
                slot=_expected_models_fact_slot(test_file),
                value=tuple(extracted_names),
            )
    return tuple(grants), tuple(faults)


def _expected_models_fact_key(
    *, test_file: DiscoveredSqlTestFile, fact_cache: FactCacheStore, syntax: SqlLexicalSyntax
) -> str:
    parts: list[str] = [str(test_file.relative_path), syntax.cache_key]
    for block in test_file.blocks:
        parts.extend((block.sql_body, block.mode.value))
    return fact_cache.key(*parts)


def _cached_expected_names(
    *, value: object, block_count: int
) -> tuple[tuple[str, ...], ...] | None:
    if not isinstance(value, tuple) or len(value) != block_count:
        return None
    for names in value:
        if not isinstance(names, tuple) or not all(isinstance(name, str) for name in names):
            return None
    return cast(tuple[tuple[str, ...], ...], value)


def _expected_models_fact_slot(test_file: DiscoveredSqlTestFile) -> str:
    return f"expected:{test_file.relative_path}"


def _scenario_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    lookup: ScopeLookup,
    shared_declarations: _SharedDeclarations,
    syntax: SqlLexicalSyntax,
) -> tuple[tuple[GrantRecord, ...], tuple[ScopeRelationshipFault, ...]]:
    grants: list[GrantRecord] = []
    faults: list[ScopeRelationshipFault] = []
    for scenario in discovered_inputs.scenario_files:
        try:
            expected_names: tuple[str, ...] = extract_sql_scenario_expected_model_names(
                sql=scenario.sql_body, file_label=str(scenario.relative_path), syntax=syntax
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
    resolution: DeclarationVisibility = resolve_scope_declaration_visibility(
        lookup=lookup, target=resource
    )
    declarations: list[DeclarationRecord] = []
    for visible in resolution.visible:
        records: tuple[DeclarationRecord, ...] = lookup.declarations.get(visible.declaration, ())
        if records and records[0].scope is not ScopeKind.PRIVATE:
            declarations.append(records[0])
    return tuple(declarations)


def _tested_macro_grants(
    *,
    lookup: ScopeLookup,
    resource: ResourceIdentity,
    sql: str,
    file_label: str,
    syntax: SqlLexicalSyntax,
) -> list[GrantRecord]:
    test_ctes: tuple[CompileSqlTestCte, ...] = extract_unclassified_sql_test_ctes(
        sql=sql, file_label=file_label, syntax=syntax
    )
    actual_cte: CompileSqlTestCte | None = next(
        (cte for cte in test_ctes if cte.name == MACRO_ACTUAL_TEST_CTE_NAME), None
    )
    if actual_cte is None:
        return []
    tested_macro_names: tuple[str, ...] = find_macro_call_names(actual_cte.sql_body)
    direct_resolution: DeclarationVisibility = resolve_scope_declaration_visibility(
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
