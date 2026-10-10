"""Relation references in the SQL-test helper CTEs a test reads, and what cannot resolve."""

from __future__ import annotations

import re
from collections.abc import Iterable
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
    SqlTestCteGraph,
    SqlTestReads,
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
_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][\w$]*")


def sql_test_cte_graph(
    *,
    authored_ctes: tuple[CompileSqlTestCte, ...],
    reader_ctes: tuple[CompileSqlTestCte, ...],
) -> SqlTestCteGraph:
    """Return the authored CTEs each test CTE reads, ignoring names its own nested CTEs define."""

    ctes: dict[str, CompileSqlTestCte] = {cte.name.casefold(): cte for cte in authored_ctes}
    keys: frozenset[str] = frozenset(ctes)
    reads: dict[str, tuple[str, ...]] = {}
    parsed_reads: dict[str, tuple[str, ...]] = {}
    for key, cte in ctes.items():
        parsed: tuple[str, ...] | None = _parsed_reads(sql=cte.sql_body, keys=keys - {key})
        parsed_reads[key] = parsed or ()
        reads[key] = (
            parsed if parsed is not None else _token_reads(sql=cte.sql_body, keys=keys - {key})
        )
    reader_reads: list[str] = []
    for reader in reader_ctes:
        parsed_reader: tuple[str, ...] | None = _parsed_reads(sql=reader.sql_body, keys=keys)
        reader_reads.extend(
            parsed_reader
            if parsed_reader is not None
            else _token_reads(sql=reader.sql_body, keys=keys)
        )
    return SqlTestCteGraph(
        ctes=ctes,
        reads=reads,
        parsed_reads=parsed_reads,
        reader_reads=tuple(dict.fromkeys(reader_reads)),
    )


def reachable_cte_keys(*, graph: SqlTestCteGraph, roots: Iterable[str]) -> tuple[str, ...]:
    """Return the authored CTEs reachable from ``roots``, including the roots, in visit order."""

    pending: list[str] = [root for root in roots if root in graph.ctes]
    visited: list[str] = list(dict.fromkeys(pending))
    while pending:
        key: str = pending.pop(0)
        for dependency in graph.reads.get(key, ()):
            if dependency not in visited:
                visited.append(dependency)
                pending.append(dependency)
    return tuple(visited)


def sql_test_reads(*, payload: CompileModelSqlTestCtes, syntax: SqlLexicalSyntax) -> SqlTestReads:
    """Return the helpers a test reads and the unmocked models they and expected rows read."""

    graph: SqlTestCteGraph = sql_test_cte_graph(
        authored_ctes=payload.authored_ctes, reader_ctes=_reader_ctes(payload)
    )
    read_helpers: tuple[str, ...] = _read_helper_keys(graph)
    mocked: frozenset[str] = frozenset(payload.mock_model_names)
    sqls: tuple[str, ...] = (
        *(cte.sql_body for cte in payload.expected_ctes),
        *(graph.ctes[key].sql_body for key in read_helpers),
    )
    targets: list[str] = []
    for sql in sqls:
        targets.extend(
            reference.ref_name
            for reference in _references(sql=sql, syntax=syntax)
            if reference.ref_kind == SqlReferenceKind.REF and reference.ref_name not in mocked
        )
    return SqlTestReads(
        read_helper_names=tuple(graph.ctes[key].name for key in read_helpers),
        reference_target_model_names=tuple(dict.fromkeys(targets)),
    )


def report_unresolvable_test_references(
    *,
    payload: CompileModelSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    known_model_names: set[str],
    syntax: SqlLexicalSyntax,
) -> bool:
    """Report unresolvable references in expected rows, assertions and read helpers, or cycles."""

    graph: SqlTestCteGraph = sql_test_cte_graph(
        authored_ctes=payload.authored_ctes, reader_ctes=_reader_ctes(payload)
    )
    read_helpers: tuple[str, ...] = _read_helper_keys(graph)
    readers: tuple[tuple[str, CompileSqlTestCte], ...] = (
        *(("helper CTE", graph.ctes[key]) for key in read_helpers),
        *(("expected CTE", cte) for cte in payload.expected_ctes),
        *(("assertion CTE", cte) for cte in payload.assertion_ctes),
    )
    reporter: _HelperDiagnostics = _HelperDiagnostics(test_file=test_file, test_block=test_block)
    mocked: dict[SqlReferenceKind, frozenset[str]] = {
        SqlReferenceKind.REF: frozenset(payload.mock_model_names),
        SqlReferenceKind.SOURCE: frozenset(payload.mock_source_names),
        SqlReferenceKind.SEED: frozenset(payload.mock_seed_names),
        SqlReferenceKind.DBT_REF: frozenset(payload.mock_dbt_ref_names),
    }
    for label, cte in readers:
        for reference in _references(sql=cte.sql_body, syntax=syntax):
            kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
            if kind not in mocked:
                continue
            mock_name: str = (
                f"{reference.ref_package}__{reference.ref_name}"
                if reference.ref_package is not None
                else reference.ref_name
            )
            if mock_name in mocked[kind]:
                continue
            if kind is SqlReferenceKind.REF:
                if reference.ref_name in known_model_names:
                    continue
                reporter.report(
                    cte_name=cte.name,
                    call=kind.example_call(reference.ref_name, quote='"'),
                    message=(
                        f"SQL test {label} '{cte.name}' references unknown model "
                        f"'{reference.ref_name}'"
                    ),
                    help=(
                        'Read a model defined in the project, for example __ref("<model>"), '
                        f"or remove the reference from {label} '{cte.name}'."
                    ),
                )
                continue
            call: str = _reference_call(reference)
            reporter.report(
                cte_name=cte.name,
                call=call,
                message=(
                    f"SQL test {label} '{cte.name}' calls {call}, which the test does not "
                    "mock, so the test query cannot resolve it"
                ),
                help=(
                    f"Mock it in the test, for example {kind.fixture_cte_prefix}{mock_name} "
                    f"AS (SELECT ...), or remove the call from {label} '{cte.name}'."
                ),
            )
    cycle: tuple[str, ...] | None = (
        _first_cycle(graph=graph, keys=reachable_cte_keys(graph=graph, roots=graph.reader_reads))
        if read_helpers
        else None
    )
    if cycle is not None:
        names: tuple[str, ...] = tuple(graph.ctes[key].name for key in cycle)
        path: str = " -> ".join(f"'{name}'" for name in names)
        reporter.report(
            cte_name=names[0],
            call=None,
            message=(
                f"SQL test CTE '{names[0]}' reads itself through {path}, so the test query "
                "cannot define its CTEs in dependency order"
            ),
            help=(
                "Break the cycle by moving the shared rows into a helper CTE that reads neither, "
                "for example shared_rows AS (SELECT ...), and read shared_rows from both CTEs."
            ),
        )
    return reporter.reported


def report_test_without_target_model(
    *,
    payload: CompileModelSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    syntax: SqlLexicalSyntax,
) -> None:
    """Report a model test whose checks read only mocks, so it would run no model."""

    mocked: dict[SqlReferenceKind, frozenset[str]] = {
        SqlReferenceKind.REF: frozenset(payload.mock_model_names),
        SqlReferenceKind.SOURCE: frozenset(payload.mock_source_names),
        SqlReferenceKind.SEED: frozenset(payload.mock_seed_names),
        SqlReferenceKind.DBT_REF: frozenset(payload.mock_dbt_ref_names),
        SqlReferenceKind.TABLE_FUNCTION: frozenset(payload.mock_table_function_names),
    }
    graph: SqlTestCteGraph = sql_test_cte_graph(
        authored_ctes=payload.authored_ctes, reader_ctes=_reader_ctes(payload)
    )
    read_mocks: list[str] = [
        graph.ctes[key].name
        for key in reachable_cte_keys(graph=graph, roots=graph.reader_reads)
        if graph.ctes[key].name.startswith(_MOCK_CTE_PREFIXES)
    ]
    first_calls: dict[SqlReferenceKind, tuple[str, str]] = {}
    called_models: set[str] = set()
    for cte in _reader_ctes(payload):
        for reference in _references(sql=cte.sql_body, syntax=syntax):
            kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
            if reference.ref_name not in mocked.get(kind, frozenset()):
                continue
            read_mocks.append(f"{kind.fixture_cte_prefix}{reference.ref_name}")
            if kind is SqlReferenceKind.REF:
                called_models.add(reference.ref_name)
            if kind is not SqlReferenceKind.TABLE_FUNCTION:
                first_calls.setdefault(kind, (cte.name, _reference_call(reference)))
    mocks: tuple[str, ...] = tuple(dict.fromkeys(read_mocks))
    mocked_models: tuple[str, ...] = tuple(
        mock.removeprefix(REF_TEST_CTE_PREFIX)
        for mock in mocks
        if mock.startswith(REF_TEST_CTE_PREFIX)
    )
    reader: CompileSqlTestCte | None = next(iter(_reader_ctes(payload)), None)
    located: tuple[str, str] | None = first_calls.get(SqlReferenceKind.REF) or (
        _mock_name_read(readers=_reader_ctes(payload), mocks=mocks)
        or next(iter(first_calls.values()), None)
    )
    test_name: str = test_block.name or test_file.relative_path.stem
    message: str
    help_text: str
    if mocked_models:
        plural: str = "s" if len(mocked_models) > 1 else ""
        owner: str = "models'" if plural else "model's"
        verb: str = "keep" if called_models.issuperset(mocked_models) else "call"
        mocked_ctes: str = ", ".join(f"{REF_TEST_CTE_PREFIX}{name}" for name in mocked_models)
        calls: str = " and ".join(
            SqlReferenceKind.REF.example_call(name, quote='"') for name in mocked_models
        )
        message = (
            f"SQL test '{test_name}' mocks the model{plural} it tests ({mocked_ctes}), so the "
            "test has no model to run against"
        )
        help_text = (
            f"Mock the {owner} inputs instead (for example __source__<source> or "
            f"__ref__<upstream model>) and {verb} {calls} in the __assert__ or __expected__ CTE, "
            "or remove the test."
        )
    else:
        reads: str = f"reads only mocks ({', '.join(mocks)})" if mocks else "reads no model"
        message = f"SQL test '{test_name}' {reads}, so the test has no model to run against"
        help_text = (
            'Call __ref("<model under test>") in an __assert__ or __expected__ CTE so the test '
            "runs that model with its mocks, or remove the test."
        )
    _HelperDiagnostics(test_file=test_file, test_block=test_block).report(
        cte_name=located[0] if located else (reader.name if reader is not None else test_name),
        call=located[1] if located else None,
        message=message,
        help=help_text,
    )


def _mock_name_read(
    *, readers: tuple[CompileSqlTestCte, ...], mocks: tuple[str, ...]
) -> tuple[str, str] | None:
    """Return the first check reading a mocked model by CTE name, with that name."""

    for mock in mocks:
        if not mock.startswith(REF_TEST_CTE_PREFIX):
            continue
        for reader in readers:
            if re.search(rf"(?<![\w$]){re.escape(mock)}(?![\w$])", reader.sql_body, re.IGNORECASE):
                return reader.name, mock
    return None


def _reader_ctes(payload: CompileModelSqlTestCtes) -> tuple[CompileSqlTestCte, ...]:
    return (*payload.expected_ctes, *payload.assertion_ctes)


def _read_helper_keys(graph: SqlTestCteGraph) -> tuple[str, ...]:
    return tuple(
        key
        for key in reachable_cte_keys(graph=graph, roots=graph.reader_reads)
        if not graph.ctes[key].name.startswith(_MOCK_CTE_PREFIXES)
    )


def _reference_call(reference: CompileSqlReference) -> str:
    kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
    if kind is SqlReferenceKind.DBT_REF and reference.ref_package is not None:
        return kind.example_call(reference.ref_package, reference.ref_name, quote='"')
    return kind.example_call(reference.ref_name, quote='"')


def _references(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[CompileSqlReference, ...]:
    return scan_sql_reference_calls(sql=sql, syntax=syntax).references


def _parsed_reads(*, sql: str, keys: frozenset[str]) -> tuple[str, ...] | None:
    """Return unqualified table reads of ``keys`` not shadowed by a nested CTE, or None."""

    folded: str = sql.casefold()
    if not any(key in folded for key in keys):
        return ()
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect="generic")
    except polyglot_module.PolyglotError:
        return None
    nested: frozenset[str] = _defined_cte_keys(parsed.to_dict())
    reads: list[str] = []
    for table in parsed.find_all("table"):
        if table.arg("schema") is not None or table.arg("catalog") is not None:
            continue
        key: str = str(getattr(table, "name", "") or "").casefold()
        if key in keys and key not in nested and key not in reads:
            reads.append(key)
    return tuple(reads)


def _defined_cte_keys(tree: Any) -> frozenset[str]:
    """Return the case-folded names of every CTE a parsed query defines, at any depth."""

    keys: set[str] = set()
    pending: list[Any] = [tree]
    while pending:
        value: Any = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
            continue
        if not isinstance(value, dict):
            continue
        ctes: Any = value.get("ctes")
        for cte in ctes if isinstance(ctes, list) else ():
            alias: Any = cte.get("alias") if isinstance(cte, dict) else None
            name: Any = alias.get("name") if isinstance(alias, dict) else None
            if isinstance(name, str):
                keys.add(name.casefold())
        pending.extend(value.values())
    return frozenset(keys)


def _token_reads(*, sql: str, keys: frozenset[str]) -> tuple[str, ...]:
    tokens: tuple[str, ...] = tuple(
        dict.fromkeys(match.casefold() for match in _IDENTIFIER_PATTERN.findall(sql))
    )
    return tuple(token for token in tokens if token in keys)


def _first_cycle(*, graph: SqlTestCteGraph, keys: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return the first parsed read cycle among ``keys``, closed on its first CTE."""

    allowed: frozenset[str] = frozenset(keys)
    for origin in keys:
        pending: list[tuple[str, ...]] = [(origin,)]
        visited: set[str] = set()
        while pending:
            path: tuple[str, ...] = pending.pop(0)
            for dependency in graph.parsed_reads.get(path[-1], ()):
                if dependency == origin:
                    return (*path, origin)
                if dependency in allowed and dependency not in visited:
                    visited.add(dependency)
                    pending.append((*path, dependency))
    return None


def sql_test_cte_location(
    *,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    cte_name: str,
    call: str | None,
) -> SourceLocation:
    """Locate a call inside one CTE of a SQL test block, else the CTE header, else the block."""

    contents: str = test_file.contents
    block_offset: int = max(contents.find(test_block.sql_body), 0)
    header: re.Match[str] | None = re.compile(
        rf"(?<![\w$]){re.escape(cte_name)}[\"`]?\s+AS\s*\(", re.IGNORECASE
    ).search(contents, block_offset)
    start: int = header.start() if header is not None else block_offset
    text: str = cte_name if header is not None else ""
    if call is not None and header is not None:
        found: re.Match[str] | None = re.compile(re.escape(call), re.IGNORECASE).search(
            contents, header.end()
        )
        if found is not None:
            start, text = found.start(), call
    return reference_call_location(
        path=test_file.relative_path, text=contents, start=start, call=text
    )


class _HelperDiagnostics:
    """Located P013 diagnostics for one SQL test block."""

    def __init__(
        self, *, test_file: DiscoveredSqlTestFile, test_block: DiscoveredSqlTestBlock
    ) -> None:
        self._test_file: DiscoveredSqlTestFile = test_file
        self._test_block: DiscoveredSqlTestBlock = test_block
        self._test_name: str = test_block.name or test_file.relative_path.stem
        self.reported: bool = False

    def report(self, *, cte_name: str, call: str | None, message: str, help: str) -> None:
        location: SourceLocation = sql_test_cte_location(
            test_file=self._test_file, test_block=self._test_block, cte_name=cte_name, call=call
        )
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
