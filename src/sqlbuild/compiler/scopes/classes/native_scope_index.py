"""A natively built scope index, materialised as the Python scope models it replaces."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlTestFile
from sqlbuild.compiler.scopes._helpers.lookup import build_lookup
from sqlbuild.compiler.scopes.classes.native_scope_rows import NativeScopeRows
from sqlbuild.compiler.scopes.exceptions import UnindexableScopeError
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    GrantRecord,
    NativeDeclarationValues,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
    ScopeLookup,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    GrantKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    UsageKind,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

type _IndexRows = tuple[
    list[str],
    list[tuple[str, str, str, str | None, str | None]],
    list[int],
    list[int],
    list[tuple[int, int]],
    list[tuple[str, str, str | None, int | None, int | None, int | None, int | None]],
    bool,
]
type _GrantRows = list[tuple[str, str, int, str | int, str]]
_RESOURCE_ROOTS: dict[ResourceKind, str] = {
    ResourceKind.MODEL: "models",
    ResourceKind.TEST: "tests/unit",
    ResourceKind.SCENARIO: "tests/scenarios",
    ResourceKind.FUNCTION: "functions/sql",
    ResourceKind.SOURCE: "sources",
}
_FIXED_ROOTS: dict[str, OwnershipRoot] = {
    "seed": OwnershipRoot("seeds", OwnershipRootKind.GLOBAL, ResourceKind.SEED),
    "python_function": OwnershipRoot(
        "functions/python", OwnershipRootKind.GLOBAL, ResourceKind.FUNCTION
    ),
}
_STATIC_COMPLETENESS: ScopeCompleteness = ScopeCompleteness(
    runtime_usage=False, relationships=False, placement=False, promotion_impact=False
)


class NativeScopeIndex:
    """One native scope index and the Python records materialised from it."""

    def __init__(self, *, native: _native.NativeScopeIndex, rows: NativeScopeRows) -> None:
        records: _IndexRows = native.records()
        paths, declaration_rows, resource_order, declaration_order, usages, diagnostics, scoped = (
            records
        )
        self._native: _native.NativeScopeIndex = native
        self._resources: list[ResourceRecord] = [
            ResourceRecord(
                identity=identity,
                path=path,
                ownership_root=_resource_root(identity=identity, root=root),
            )
            for identity, path, root in zip(
                rows.resource_identities, paths, rows.resource_roots, strict=True
            )
        ]
        self._declarations: list[DeclarationRecord] = [
            _declaration_record(values=values, row=row)
            for values, row in zip(rows.declaration_values, declaration_rows, strict=True)
        ]
        self._usages: list[UsageRecord] = [
            UsageRecord(
                consumer=self._declarations[consumer].identity,
                declaration=rows.declaration_values[consumer].dependencies[dependency],
                kind=UsageKind.DECLARATION_DEPENDENCY,
            )
            for consumer, dependency in usages
        ]
        self._grants: list[GrantRecord] = []
        self.has_scoped_relationship_declarations: bool = scoped
        self.index: ScopeIndex = ScopeIndex(
            ownership_roots=tuple(
                OwnershipRoot(path=path, resource_kind=kind)
                for kind, path in sorted(_RESOURCE_ROOTS.items(), key=lambda item: item[1])
            ),
            resources=tuple(self._resources[position] for position in resource_order),
            declarations=tuple(self._declarations[position] for position in declaration_order),
            usages=tuple(self._usages),
            diagnostics=tuple(
                ScopeDiagnostic(
                    ScopeDiagnosticCode(code),
                    message,
                    path=path,
                    line=line,
                    column=column,
                    declaration=(
                        None if declaration is None else self._declarations[declaration].identity
                    ),
                    resource=None if resource is None else self._resources[resource].identity,
                )
                for code, message, path, line, column, declaration, resource in diagnostics
            ),
            completeness=_STATIC_COMPLETENESS,
        )

    def grant_relationships(
        self,
        *,
        discovered_inputs: DiscoveredProjectInputs,
        syntax: SqlLexicalSyntax,
        scan_store: tuple[_native.SqlTestScanStore | None, str],
    ) -> tuple[tuple[Path, str], ...]:
        """Grant every test's and scenario's relationships; return each extraction fault."""

        store, algorithm = scan_store
        rows, faults = self._native.grant_relationships(
            [_test_file_row(test_file) for test_file in discovered_inputs.test_files],
            [
                (scenario.name, str(scenario.relative_path), scenario.sql_body)
                for scenario in discovered_inputs.scenario_files
            ],
            {
                "syntax": syntax.native_mapping,
                "store": store,
                "scan_key": (algorithm, syntax.cache_key),
            },
        )
        if rows is None:
            raise UnindexableScopeError
        identities: dict[tuple[str, str], ResourceIdentity] = {}
        self._grants = [
            GrantRecord(
                resource=identities.setdefault(
                    (kind, name), ResourceIdentity(ResourceKind(kind), name)
                ),
                declaration=self._declarations[declaration].identity,
                through=(
                    ResourceIdentity(ResourceKind.MODEL, through)
                    if isinstance(through, str)
                    else self._declarations[through].identity
                ),
                kind=GrantKind(grant_kind),
            )
            for kind, name, declaration, through, grant_kind in rows
        ]
        return tuple((Path(path), message) for path, message in faults)

    def index_with_relationships(self) -> ScopeIndex:
        """Return the index with its grants attached and relationships complete."""

        return replace(
            self.index,
            grants=tuple(self._grants),
            completeness=replace(self.index.completeness, relationships=True),
        )

    def lookup(self, *, index: ScopeIndex) -> ScopeLookup:
        """The native scope lookup of `index_with_relationships()`."""

        return build_lookup(index=index)


def _test_file_row(
    test_file: DiscoveredSqlTestFile,
) -> tuple[str, list[tuple[str, str, str]]]:
    stem: str = test_file.relative_path.stem
    return (
        str(test_file.relative_path),
        [(block.name or stem, block.sql_body, block.mode.value) for block in test_file.blocks],
    )


def _resource_root(*, identity: ResourceIdentity, root: str) -> OwnershipRoot:
    fixed: OwnershipRoot | None = _FIXED_ROOTS.get(root)
    if fixed is not None:
        return fixed
    return OwnershipRoot(path=_RESOURCE_ROOTS[identity.kind], resource_kind=identity.kind)


def _declaration_record(
    *, values: NativeDeclarationValues, row: tuple[str, str, str, str | None, str | None]
) -> DeclarationRecord:
    path, root_path, root_kind, root_resource_kind, owning_path = row
    return DeclarationRecord(
        identity=values.identity,
        path=path,
        line=values.line,
        column=1,
        scope=values.scope,
        ownership_root=OwnershipRoot(
            root_path,
            OwnershipRootKind(root_kind),
            None if root_resource_kind is None else ResourceKind(root_resource_kind),
        ),
        owning_path=owning_path,
        macro=values.macro,
        enum=values.enum,
        constant=values.constant,
    )
