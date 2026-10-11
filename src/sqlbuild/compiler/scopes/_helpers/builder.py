"""Tolerant scope snapshots built by the native scope index from partial discovery."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.constants import SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM
from sqlbuild.compiler.compile.main._static_macro_inventory import inventory_project_macros
from sqlbuild.compiler.compile.models import StaticMacroInventory
from sqlbuild.compiler.discovery.main._scope_snapshot import discover_scope_snapshot
from sqlbuild.compiler.discovery.models import DiscoveryFileFault, TolerantScopeDiscovery
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.models import (
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
)
from sqlbuild.compiler.scopes.types import ResourceKind, ScopeDiagnosticCode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_ROOTS: dict[ResourceKind, str] = {
    ResourceKind.MODEL: "models",
    ResourceKind.TEST: "tests/unit",
    ResourceKind.SCENARIO: "tests/scenarios",
    ResourceKind.FUNCTION: "functions/sql",
    ResourceKind.SOURCE: "sources",
}


def build_tolerant_scope_index(
    *, project_dir: Path, sql_lexical_syntax: SqlLexicalSyntax
) -> ScopeIndex:
    """Build a partial static index from published tolerant compiler facts."""

    snapshot: TolerantScopeDiscovery = discover_scope_snapshot(project_dir=project_dir)
    macro_inventory: StaticMacroInventory = inventory_project_macros(
        macro_files=snapshot.discovered_inputs.macro_files
    )
    native: NativeScopeIndex = open_native_scope_index(
        discovered_inputs=snapshot.discovered_inputs,
        loaded_macros={},
        static_macros=macro_inventory.exports,
    )
    relationship_faults: tuple[tuple[Path, str], ...] = native.grant_relationships(
        discovered_inputs=snapshot.discovered_inputs,
        syntax=sql_lexical_syntax,
        scan_store=(None, SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM),
    )
    index: ScopeIndex = native.index_with_relationships()
    diagnostics: tuple[ScopeDiagnostic, ...] = _tolerant_diagnostics(
        snapshot=snapshot,
        macro_inventory=macro_inventory,
        relationship_faults=relationship_faults,
    )
    prospective: tuple[ResourceRecord, ...] = tuple(
        record
        for fault in (*snapshot.resource_faults, *snapshot.relationship_faults)
        if fault.path is not None
        if (record := _prospective_resource(path=fault.path)) is not None
    )
    return replace(
        index,
        resources=tuple(
            sorted(
                dict.fromkeys((*index.resources, *prospective)),
                key=_resource_key,
            )
        ),
        diagnostics=tuple(
            sorted(
                (*index.diagnostics, *diagnostics),
                key=_diagnostic_key,
            )
        ),
        completeness=ScopeCompleteness(
            discovery=False,
            static_visibility=not (
                snapshot.declaration_faults or snapshot.config_faults or macro_inventory.faults
            ),
            runtime_usage=False,
            relationships=not snapshot.relationship_faults and not relationship_faults,
            placement=False,
            promotion_impact=False,
        ),
    )


def _tolerant_diagnostics(
    *,
    snapshot: TolerantScopeDiscovery,
    macro_inventory: StaticMacroInventory,
    relationship_faults: tuple[tuple[Path, str], ...],
) -> tuple[ScopeDiagnostic, ...]:
    diagnostics: list[ScopeDiagnostic] = []
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.RESOURCE_PARSE_ERROR)
        for fault in snapshot.resource_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.DECLARATION_PARSE_ERROR)
        for fault in snapshot.declaration_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.RELATIONSHIP_PARSE_ERROR)
        for fault in snapshot.relationship_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.CONFIG_PARSE_ERROR)
        for fault in snapshot.config_faults
    )
    diagnostics.extend(
        ScopeDiagnostic(
            ScopeDiagnosticCode.MACRO_PARSE_ERROR,
            fault.message,
            path=fault.relative_path.as_posix(),
        )
        for fault in macro_inventory.faults
    )
    diagnostics.extend(
        ScopeDiagnostic(
            ScopeDiagnosticCode.RELATIONSHIP_PARSE_ERROR,
            message,
            path=path.as_posix(),
        )
        for path, message in relationship_faults
    )
    return tuple(diagnostics)


def _discovery_diagnostic(
    *, fault: DiscoveryFileFault, code: ScopeDiagnosticCode
) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        code,
        fault.message,
        path=fault.path.as_posix() if fault.path is not None else None,
    )


def _prospective_resource(*, path: Path) -> ResourceRecord | None:
    relative: str = path.as_posix()
    for kind, root in _ROOTS.items():
        if relative.startswith(f"{root}/"):
            return ResourceRecord(
                ResourceIdentity(kind, path.stem),
                relative,
                OwnershipRoot(root, resource_kind=kind),
            )
    return None


def _resource_key(record: ResourceRecord) -> tuple[str, str, str]:
    return (record.path, record.identity.kind.value, record.identity.name)


def _diagnostic_key(item: ScopeDiagnostic) -> tuple[str, int, int, str, str]:
    return (item.path or "", item.line or 0, item.column or 0, item.code.value, item.message)
