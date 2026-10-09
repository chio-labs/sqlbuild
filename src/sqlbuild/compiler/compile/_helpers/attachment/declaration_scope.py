"""Build process-local declaration scope state for one compile invocation."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import CodeType

from sqlbuild.compiler.compile._helpers.attachment.scope_relationships import (
    build_scope_relationship_grants,
    extract_scope_relationship_facts,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_declaration_scope_resolver,
)
from sqlbuild.compiler.compile._helpers.sql_tests.extraction_errors import (
    validate_authored_scenario_cte_names,
    validate_authored_test_cte_names,
)
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationScopeBuild,
    LoadedMacro,
    ScopeRelationshipBuild,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex
from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.main._build_scope_index import build_scope_index
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.main._validate_scope_index import validate_scope_index
from sqlbuild.compiler.scopes.models import RelationshipFact, ScopeIndex, ScopeLookup
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def build_declaration_scope(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
    sql_lexical_syntax: SqlLexicalSyntax,
    compile_cache_dir: Path | None = None,
) -> DeclarationScopeBuild:
    """Build one canonical index and validate it before SQL expansion."""

    scan_cache: SqlTestScanCache = SqlTestScanCache(cache_dir=compile_cache_dir)

    validate_authored_test_cte_names(
        test_files=discovered_inputs.test_files, syntax=sql_lexical_syntax
    )
    validate_authored_scenario_cte_names(
        scenario_files=discovered_inputs.scenario_files, syntax=sql_lexical_syntax
    )
    if native_stage_enabled(NativeStage.DECLARATION_SCOPES):
        native_scope: DeclarationScopeBuild | None = _build_native_declaration_scope(
            discovered_inputs=discovered_inputs,
            loaded_macros=loaded_macros,
            sql_lexical_syntax=sql_lexical_syntax,
            scan_cache=scan_cache,
        )
        if native_scope is not None:
            return native_scope
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
            sql_lexical_syntax=sql_lexical_syntax,
            scan_cache=scan_cache,
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
        sql_test_scans=scan_cache,
    )


def _build_native_declaration_scope(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: dict[str, LoadedMacro],
    sql_lexical_syntax: SqlLexicalSyntax,
    scan_cache: SqlTestScanCache,
) -> DeclarationScopeBuild | None:
    """Build the scope natively with Python's errors and order, or None for the Python stage."""

    native: NativeScopeIndex | None = open_native_scope_index(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
    )
    if native is None:
        report_native_fallback(site=NativeFallbackSite.SCOPE_INDEX)
        return None
    try:
        validate_scope_index(index=native.index)
    except ScopeValidationError as error:
        raise CompileInputError(str(error)) from error
    if native.has_scoped_relationship_declarations and (
        discovered_inputs.test_files or discovered_inputs.scenario_files
    ):
        facts: tuple[RelationshipFact, ...]
        fault: str | None
        facts, fault = extract_scope_relationship_facts(
            discovered_inputs=discovered_inputs,
            sql_lexical_syntax=sql_lexical_syntax,
            scan_cache=scan_cache,
        )
        if fault is not None:
            raise CompileInputError(fault, bridge_independent=True)
        if not native.grant(facts):
            report_native_fallback(site=NativeFallbackSite.SCOPE_GRANTS)
            return None
    index: ScopeIndex = native.index_with_relationships()
    lookup: ScopeLookup | None = native.lookup(index=index)
    if lookup is None:
        report_native_fallback(site=NativeFallbackSite.SCOPE_LOOKUP)
        return None
    report_native_answer(stage=NativeStage.DECLARATION_SCOPES, kind="scope_indexes")
    return DeclarationScopeBuild(
        loaded_macros=loaded_macros,
        index=index,
        resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=index,
            loaded_macros=loaded_macros,
            lookup=lookup,
        ),
        sql_test_scans=scan_cache,
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
        sql_test_scans=scope.sql_test_scans,
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
