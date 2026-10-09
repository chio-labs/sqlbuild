"""Expected-model declaration grants with tolerant relationship faults."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import cast

import orjson

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
from sqlbuild.compiler.compile._helpers.sql_tests.native import native_sql_test_ctes
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.constants import (
    MACRO_ACTUAL_TEST_CTE_NAME,
    SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
    ScopeRelationshipBuild,
    ScopeRelationshipFault,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlTestFile
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
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
type _BlockNames = tuple[str, ...] | Exception


def build_scope_relationship_grants(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    index: ScopeIndex,
    sql_lexical_syntax: SqlLexicalSyntax,
    scan_cache: SqlTestScanCache | None = None,
) -> ScopeRelationshipBuild:
    """Return expected-model grants while retaining independent extraction faults."""

    lookup: ScopeLookup = build_scope_lookup(index=index)
    shared_declarations: _SharedDeclarations = _shared_declarations_by_directory(lookup=lookup)
    test_grants, test_faults = _test_relationship_grants(
        discovered_inputs=discovered_inputs,
        lookup=lookup,
        shared_declarations=shared_declarations,
        scan_cache=scan_cache or SqlTestScanCache(cache_dir=None),
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
    scan_cache: SqlTestScanCache | None = None,
) -> tuple[tuple[RelationshipFact, ...], str | None]:
    """Return the relationship names grants are resolved from, and the first extraction fault."""

    facts: list[RelationshipFact] = []
    faults: list[ScopeRelationshipFault] = []
    names_by_file: list[list[_BlockNames]] = _expected_names_by_file(
        test_files=discovered_inputs.test_files,
        scan_cache=scan_cache or SqlTestScanCache(cache_dir=None),
        syntax=sql_lexical_syntax,
        scan_natively=True,
    )
    macro_blocks: list[tuple[str, str]] = []
    for test_file in discovered_inputs.test_files:
        macro_blocks.extend(
            (block.sql_body, str(test_file.relative_path))
            for block in test_file.blocks
            if block.mode is SqlTestMode.MACRO
        )
    macro_test_ctes: Iterator[tuple[tuple[str, str], ...] | str | None] = iter(
        native_sql_test_ctes(texts=macro_blocks, syntax=sql_lexical_syntax)
    )
    for test_file, file_names in zip(discovered_inputs.test_files, names_by_file, strict=True):
        for block, block_names in zip(test_file.blocks, file_names, strict=True):
            native_ctes: tuple[tuple[str, str], ...] | str | None = (
                next(macro_test_ctes) if block.mode is SqlTestMode.MACRO else None
            )
            try:
                expected_names: tuple[str, ...] = _names_or_raise(block_names)
                called_macros: tuple[str, ...] = find_nested_macro_call_names(block.sql_body)
                facts.append(
                    RelationshipFact(
                        resource=ResourceIdentity(
                            ResourceKind.TEST, block.name or test_file.relative_path.stem
                        ),
                        expected_models=expected_names,
                        called_macros=called_macros,
                        tested_macros=(
                            _natively_tested_macro_names(
                                native_ctes=native_ctes,
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
    scenario_names: list[tuple[str, ...] | str | None] = native_expected_model_names(
        texts=[
            (scenario.sql_body, str(scenario.relative_path))
            for scenario in discovered_inputs.scenario_files
        ],
        scenario=True,
        syntax=sql_lexical_syntax,
    )
    for scenario, scanned in zip(discovered_inputs.scenario_files, scenario_names, strict=True):
        if isinstance(scanned, str):
            faults.append(ScopeRelationshipFault(scenario.relative_path, scanned))
            continue
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


def _expected_names_by_file(
    *,
    test_files: Sequence[DiscoveredSqlTestFile],
    scan_cache: SqlTestScanCache,
    syntax: SqlLexicalSyntax,
    scan_natively: bool,
) -> list[list[_BlockNames]]:
    """Return each block's expected-model names or extraction error, reusing whole stored files."""

    stored: list[tuple[tuple[str, ...], ...] | None] = [
        scan_cache.read(
            algorithm=SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM,
            syntax=syntax,
            parts=_expected_names_parts(test_file),
            decode=_stored_expected_names(block_count=len(test_file.blocks)),
        )
        for test_file in test_files
    ]
    scanned: dict[tuple[int, int], _BlockNames] = (
        _scanned_expected_names(test_files=test_files, stored=stored, syntax=syntax)
        if scan_natively
        else {}
    )
    names_by_file: list[list[_BlockNames]] = []
    for file_index, test_file in enumerate(test_files):
        stored_names: tuple[tuple[str, ...], ...] | None = stored[file_index]
        if stored_names is not None:
            names_by_file.append(list(stored_names))
            continue
        file_names: list[_BlockNames] = []
        for block_index, block in enumerate(test_file.blocks):
            native_names: _BlockNames | None = scanned.get((file_index, block_index))
            if native_names is not None:
                file_names.append(native_names)
                continue
            if scan_natively:
                report_native_fallback(
                    site=NativeFallbackSite.SCOPE_RELATIONSHIP_CTES, kind="expected_names"
                )
            try:
                file_names.append(
                    extract_sql_test_expected_model_names(
                        sql=block.sql_body,
                        file_label=str(test_file.relative_path),
                        syntax=syntax,
                        mode=block.mode,
                    )
                )
            except Exception as error:
                file_names.append(error)
        if not any(isinstance(names, Exception) for names in file_names):
            scan_cache.write(
                algorithm=SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM,
                syntax=syntax,
                parts=_expected_names_parts(test_file),
                value=orjson.dumps(file_names),
            )
        names_by_file.append(file_names)
    return names_by_file


def _expected_names_parts(test_file: DiscoveredSqlTestFile) -> list[str]:
    parts: list[str] = [str(test_file.relative_path)]
    for block in test_file.blocks:
        parts.extend((block.sql_body, block.mode.value))
    return parts


def _stored_expected_names(
    *, block_count: int
) -> Callable[[bytes], tuple[tuple[str, ...], ...] | None]:
    """Decode one file's stored names, rejecting anything that is not their exact shape."""

    def decode(value: bytes) -> tuple[tuple[str, ...], ...] | None:
        try:
            decoded: object = orjson.loads(value)
        except orjson.JSONDecodeError:
            return None
        if not isinstance(decoded, list) or len(cast(list[object], decoded)) != block_count:
            return None
        blocks: list[tuple[str, ...]] = []
        for names in cast(list[object], decoded):
            if not isinstance(names, list) or not all(
                isinstance(name, str) for name in cast(list[object], names)
            ):
                return None
            blocks.append(tuple(cast(list[str], names)))
        return tuple(blocks)

    return decode


def _names_or_raise(names: _BlockNames) -> tuple[str, ...]:
    if isinstance(names, Exception):
        raise names
    return names


def _scanned_expected_names(
    *,
    test_files: Sequence[DiscoveredSqlTestFile],
    stored: Sequence[tuple[tuple[str, ...], ...] | None],
    syntax: SqlLexicalSyntax,
) -> dict[tuple[int, int], _BlockNames]:
    """Scan model-mode blocks of unstored files natively: names or Python's error, where exact."""

    pending: list[tuple[int, int]] = []
    for file_index, test_file in enumerate(test_files):
        if stored[file_index] is not None:
            continue
        pending.extend(
            (file_index, block_index)
            for block_index, block in enumerate(test_file.blocks)
            if block.mode is SqlTestMode.MODEL
        )
    scanned: list[tuple[str, ...] | str | None] = native_expected_model_names(
        texts=[
            (
                test_files[file_index].blocks[block_index].sql_body,
                str(test_files[file_index].relative_path),
            )
            for file_index, block_index in pending
        ],
        scenario=False,
        syntax=syntax,
    )
    return {
        position: CompileInputError(names, bridge_independent=True)
        if isinstance(names, str)
        else names
        for position, names in zip(pending, scanned, strict=True)
        if names is not None
    }


def _natively_tested_macro_names(
    *,
    native_ctes: tuple[tuple[str, str], ...] | str | None,
    sql: str,
    file_label: str,
    syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    """Macros a macro test's actual CTE calls, scanned natively where Python's scanner is exact."""

    if native_ctes is None:
        report_native_fallback(site=NativeFallbackSite.SCOPE_RELATIONSHIP_CTES, kind="macro_test")
        return _tested_macro_names(sql=sql, file_label=file_label, syntax=syntax)
    if isinstance(native_ctes, str):
        raise CompileInputError(native_ctes, bridge_independent=True)
    actual_sql: str | None = next(
        (body for name, body in native_ctes if name == MACRO_ACTUAL_TEST_CTE_NAME), None
    )
    return () if actual_sql is None else find_macro_call_names(actual_sql)


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
    scan_cache: SqlTestScanCache,
    syntax: SqlLexicalSyntax,
) -> tuple[tuple[GrantRecord, ...], tuple[ScopeRelationshipFault, ...]]:
    grants: list[GrantRecord] = []
    faults: list[ScopeRelationshipFault] = []
    names_by_file: list[list[_BlockNames]] = _expected_names_by_file(
        test_files=discovered_inputs.test_files,
        scan_cache=scan_cache,
        syntax=syntax,
        scan_natively=False,
    )
    for test_file, file_names in zip(discovered_inputs.test_files, names_by_file, strict=True):
        for block, block_names in zip(test_file.blocks, file_names, strict=True):
            try:
                expected_names: tuple[str, ...] = _names_or_raise(block_names)
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
    return tuple(grants), tuple(faults)


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
