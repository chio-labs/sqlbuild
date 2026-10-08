"""Relation references in SQL-test helper CTEs: the models they read and what cannot resolve."""

from __future__ import annotations

import re
from typing import Any

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.refs.references import (
    reference_call_location,
    scan_sql_reference_calls,
)
from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SQL_TEST_HELPER_REFERENCE_CODE,
    TABLE_FN_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.models import (
    CompileModelSqlTestCtes,
    CompilerDiagnostic,
    CompileSqlReference,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SourceLocation

_MOCK_CTE_PREFIXES: tuple[str, ...] = (
    REF_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    TABLE_FN_TEST_CTE_PREFIX,
)
_RELATION_REFERENCE_KINDS: frozenset[SqlReferenceKind] = frozenset(
    {
        SqlReferenceKind.REF,
        SqlReferenceKind.SOURCE,
        SqlReferenceKind.SEED,
        SqlReferenceKind.DBT_REF,
        SqlReferenceKind.TABLE_FUNCTION,
    }
)


def sql_test_helper_ctes(
    authored_ctes: tuple[CompileSqlTestCte, ...],
) -> tuple[CompileSqlTestCte, ...]:
    """Return the authored CTEs that are helpers rather than mocks or fixtures."""

    return tuple(cte for cte in authored_ctes if not cte.name.startswith(_MOCK_CTE_PREFIXES))


def extract_helper_target_model_names(
    *,
    helper_ctes: tuple[CompileSqlTestCte, ...],
    mock_model_names: tuple[str, ...],
    syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    """Return unmocked models helper CTEs read with ``__ref()``, which the test must run."""

    mocked: frozenset[str] = frozenset(mock_model_names)
    targets: list[str] = []
    for cte in helper_ctes:
        targets.extend(
            reference.ref_name
            for reference in _references(sql=cte.sql_body, syntax=syntax)
            if reference.ref_kind == SqlReferenceKind.REF and reference.ref_name not in mocked
        )
    return tuple(dict.fromkeys(targets))


def report_unresolvable_helper_ctes(
    *,
    model_payload: CompileModelSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    known_model_names: set[str],
    syntax: SqlLexicalSyntax,
) -> bool:
    """Report helper CTEs the test query cannot place or resolve; return whether any was found."""

    helper_ctes: tuple[CompileSqlTestCte, ...] = sql_test_helper_ctes(model_payload.authored_ctes)
    if not helper_ctes:
        return False
    reporter: _HelperDiagnostics = _HelperDiagnostics(test_file=test_file, test_block=test_block)
    mocked: frozenset[str] = frozenset(model_payload.mock_model_names)
    for cte in helper_ctes:
        for reference in _references(sql=cte.sql_body, syntax=syntax):
            if (
                reference.ref_kind == SqlReferenceKind.REF
                and reference.ref_name not in mocked
                and reference.ref_name not in known_model_names
            ):
                reporter.report(
                    cte_name=cte.name,
                    call=SqlReferenceKind.REF.example_call(reference.ref_name, quote='"'),
                    message=(
                        f"SQL test helper CTE '{cte.name}' references unknown model "
                        f"'{reference.ref_name}'"
                    ),
                    help=(
                        'Read a model defined in the project, for example __ref("<model>"), '
                        f"or remove the reference from helper CTE '{cte.name}'."
                    ),
                )
    dependencies: dict[str, tuple[str, ...]] = _authored_cte_dependencies(
        authored_ctes=model_payload.authored_ctes
    )
    names_by_key: dict[str, str] = {
        cte.name.casefold(): cte.name for cte in model_payload.authored_ctes
    }
    cycle: tuple[str, ...] | None = _first_cycle(dependencies)
    if cycle is not None:
        path: str = " -> ".join(f"'{names_by_key[key]}'" for key in cycle)
        reporter.report(
            cte_name=names_by_key[cycle[0]],
            call=None,
            message=(
                f"SQL test CTE '{names_by_key[cycle[0]]}' reads itself through {path}, so the "
                "test query cannot define its CTEs in dependency order"
            ),
            help=(
                "Break the cycle by moving the shared rows into a helper CTE that reads neither, "
                "for example shared_rows AS (SELECT ...), and read shared_rows from both CTEs."
            ),
        )
    _report_mocks_reading_references(
        reporter=reporter,
        model_payload=model_payload,
        helper_ctes=helper_ctes,
        dependencies=dependencies,
        syntax=syntax,
    )
    return reporter.reported


class _HelperDiagnostics:
    """Located P013 diagnostics for one SQL test block."""

    def __init__(
        self, *, test_file: DiscoveredSqlTestFile, test_block: DiscoveredSqlTestBlock
    ) -> None:
        self._test_file: DiscoveredSqlTestFile = test_file
        self._block_offset: int = max(test_file.contents.find(test_block.sql_body), 0)
        self._test_name: str = test_block.name or test_file.relative_path.stem
        self.reported: bool = False

    def report(self, *, cte_name: str, call: str | None, message: str, help: str) -> None:
        location: SourceLocation = self._location(cte_name=cte_name, call=call)
        self.reported = True
        report_compile_diagnostic(
            key=(
                SQL_TEST_HELPER_REFERENCE_CODE,
                self._test_file.relative_path.as_posix(),
                f"{location.line:09d}:{location.column:09d}",
                message,
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=SQL_TEST_HELPER_REFERENCE_CODE,
                message=message,
                resource_type=CompiledResourceType.SQL_TEST,
                resource_name=self._test_name,
                location=location,
                help=help,
            ),
        )

    def _location(self, *, cte_name: str, call: str | None) -> SourceLocation:
        contents: str = self._test_file.contents
        header: re.Match[str] | None = re.compile(
            rf"(?<![\w$]){re.escape(cte_name)}[\"`]?\s+AS\s*\(", re.IGNORECASE
        ).search(contents, self._block_offset)
        start: int = header.start() if header is not None else self._block_offset
        text: str = cte_name if header is not None else ""
        if call is not None and header is not None:
            found: re.Match[str] | None = re.compile(re.escape(call), re.IGNORECASE).search(
                contents, header.end()
            )
            if found is not None:
                start, text = found.start(), call
        return reference_call_location(
            path=self._test_file.relative_path, text=contents, start=start, call=text
        )


def _report_mocks_reading_references(
    *,
    reporter: _HelperDiagnostics,
    model_payload: CompileModelSqlTestCtes,
    helper_ctes: tuple[CompileSqlTestCte, ...],
    dependencies: dict[str, tuple[str, ...]],
    syntax: SqlLexicalSyntax,
) -> None:
    referencing: dict[str, tuple[CompileSqlTestCte, CompileSqlReference]] = {}
    for cte in helper_ctes:
        reference: CompileSqlReference | None = next(
            (
                reference
                for reference in _references(sql=cte.sql_body, syntax=syntax)
                if reference.ref_kind in _RELATION_REFERENCE_KINDS
            ),
            None,
        )
        if reference is not None:
            referencing[cte.name.casefold()] = (cte, reference)
    if not referencing:
        return
    for mock in model_payload.authored_ctes:
        if not mock.name.startswith(_MOCK_CTE_PREFIXES):
            continue
        helper_key: str | None = _first_reachable(
            origin=mock.name.casefold(), targets=referencing, dependencies=dependencies
        )
        if helper_key is None:
            continue
        helper, reference = referencing[helper_key]
        call: str = _reference_call(reference)
        reporter.report(
            cte_name=helper.name,
            call=call,
            message=(
                f"SQL test mock '{mock.name}' reads helper CTE '{helper.name}', which calls "
                f"{call}; mocks and fixtures are defined before the models the test runs, so "
                "the helper cannot be resolved for them"
            ),
            help=_mock_reference_help(mock_name=mock.name, call=call, reference=reference),
        )


def _mock_reference_help(*, mock_name: str, call: str, reference: CompileSqlReference) -> str:
    kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
    if kind is not SqlReferenceKind.TABLE_FUNCTION and reference.ref_package is None:
        mock_cte: str = f"{kind.fixture_cte_prefix}{reference.ref_name}"
        return (
            f"Read a mock by its CTE name instead, for example FROM {mock_cte} rather than "
            f"FROM {call}, defining {mock_cte} AS (SELECT ...) if the test does not mock it, "
            f"or write the rows of '{mock_name}' directly."
        )
    return f"Write the rows of '{mock_name}' directly, for example {mock_name} AS (SELECT ...)."


def _reference_call(reference: CompileSqlReference) -> str:
    kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
    if kind is SqlReferenceKind.DBT_REF and reference.ref_package is not None:
        return kind.example_call(reference.ref_package, reference.ref_name, quote='"')
    return kind.example_call(reference.ref_name, quote='"')


def _references(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[CompileSqlReference, ...]:
    return scan_sql_reference_calls(sql=sql, syntax=syntax).references


def _authored_cte_dependencies(
    *, authored_ctes: tuple[CompileSqlTestCte, ...]
) -> dict[str, tuple[str, ...]]:
    """Return each authored CTE's unqualified table reads of other authored CTEs."""

    keys: frozenset[str] = frozenset(cte.name.casefold() for cte in authored_ctes)
    dependencies: dict[str, tuple[str, ...]] = {}
    for cte in authored_ctes:
        key: str = cte.name.casefold()
        references: tuple[str, ...] = _table_reference_keys(sql=cte.sql_body, keys=keys)
        dependencies[key] = tuple(reference for reference in references if reference != key)
    return dependencies


def _table_reference_keys(*, sql: str, keys: frozenset[str]) -> tuple[str, ...]:
    folded: str = sql.casefold()
    if not any(key in folded for key in keys):
        return ()
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect="generic")
    except polyglot_module.PolyglotError:
        return ()
    references: list[str] = []
    for table in parsed.find_all("table"):
        if table.arg("schema") is not None or table.arg("catalog") is not None:
            continue
        key: str = str(getattr(table, "name", "") or "").casefold()
        if key in keys and key not in references:
            references.append(key)
    return tuple(references)


def _first_cycle(dependencies: dict[str, tuple[str, ...]]) -> tuple[str, ...] | None:
    """Return the first dependency cycle in authored order, closed on its first node."""

    for origin in dependencies:
        pending: list[tuple[str, ...]] = [(origin,)]
        visited: set[str] = set()
        while pending:
            path: tuple[str, ...] = pending.pop(0)
            for dependency in dependencies.get(path[-1], ()):
                if dependency == origin:
                    return (*path, origin)
                if dependency not in visited:
                    visited.add(dependency)
                    pending.append((*path, dependency))
    return None


def _first_reachable(
    *,
    origin: str,
    targets: dict[str, tuple[CompileSqlTestCte, CompileSqlReference]],
    dependencies: dict[str, tuple[str, ...]],
) -> str | None:
    pending: list[str] = list(dependencies.get(origin, ()))
    visited: set[str] = set(pending)
    while pending:
        key: str = pending.pop(0)
        if key in targets:
            return key
        for dependency in dependencies.get(key, ()):
            if dependency not in visited:
                visited.add(dependency)
                pending.append(dependency)
    return None
