"""Generated reference SQL and native-versus-Python comparison for reference extraction."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from itertools import chain, compress
from operator import attrgetter, itemgetter
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile._helpers.diagnostics.collector import collect_compile_diagnostics
from sqlbuild.compiler.compile._helpers.refs.native import extract_native_sql_references
from sqlbuild.compiler.compile._helpers.refs.references import (
    extract_sql_references,
    python_reference_scan,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    CompileSqlReference,
    ExpansionSpan,
    SqlReferenceOrigin,
    SqlReferenceScan,
    SqlReferenceSourceMap,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlReferenceScanFailure
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

LEXICAL_SYNTAXES: dict[str, SqlLexicalSyntax] = {
    "generic": SqlLexicalSyntax(),
    "bigquery": BigQueryAdapter.sql_lexical_syntax,
    "databricks": DatabricksAdapter.sql_lexical_syntax,
    "duckdb": DuckDbAdapter.sql_lexical_syntax,
    "postgres": PostgresAdapter.sql_lexical_syntax,
    "snowflake": SnowflakeAdapter.sql_lexical_syntax,
    "sqlserver": SqlServerAdapter.sql_lexical_syntax,
}
_NAMES: tuple[str, ...] = (
    '"orders"',
    '"customers"',
    '"order items"',
    '"größe"',
)
_REJECTED_NAMES: tuple[str, ...] = (
    "'customers'",
    "products",
    "  inventory\t",
    "'commandés'",
    "orders\x1c",
    "orders /* note */",
    "-- note\norders",
    ' "orders" ',
    ' "order""s" ',
    '"a" "b"',
    '""',
    '/* note */ "orders"',
)
_MALFORMED_NAMES: tuple[str, ...] = (
    "'x\"",
    "1orders",
    "_orders",
    "order-items",
    "commandés",
    "\u00a0orders",
    "concat('a', 'b')",
    '__ref("orders")',
    "",
    " ",
    "/* only */",
    "'orders'",
    "orders",
)
_NO_SECOND_ARGUMENT: tuple[str, ...] = ("",)
_DBT_SECOND_ARGUMENTS: tuple[str, ...] = ("", ', "products"', ' ,\x1c"orders"', ", products")
_MALFORMED_SECOND_ARGUMENTS: tuple[str, ...] = (",", ", ", ",, products", ", products", ' ,"a"')
_NO_CALL_SUFFIX: tuple[str, ...] = ("",)
_CALL_SUFFIXES: tuple[str, ...] = (
    "()",
    "(1)",
    " (1, 2)",
    "\n(f(1, 2), 'a,b')",
    "((SELECT 1), $$a,b$$)",
    '(__ref("orders"))',
    "(1 /* , */, 2 -- ,\n)",
    "\x1c(1)",
)
_MALFORMED_CALL_SUFFIXES: tuple[str, ...] = (
    "(1,)",
    "(, 1)",
    "/* gap */ (1)",
    "\u00a0(1)",
    "",
    "(1",
    " x",
)
_FILLERS: tuple[str, ...] = (
    "SELECT * FROM ",
    " JOIN ",
    "\n",
    "'__ref(\"hidden\")'",
    '"quoted__ref(x)"',
    "`tick__ref(x)`",
    "$$ __ref(hidden) $$",
    "$tag$ __table_fn(hidden) $tag$",
    "-- __ref(hidden)\n",
    "/* __ref(hidden) */",
    "'it''s'",
    "a$$b",
    "é",
    "/* unclosed",
    "'unclosed",
)
_RISKY_FILLERS: tuple[str, ...] = (
    "# __ref(hidden)\n",
    "// __ref(hidden)\n",
    "/* outer /* inner */ __ref(nested) */",
    "'it\\'s __ref(escaped)'",
    "E'it\\'s __ref(escaped)'",
    "r'C:\\' __ref(raw)",
    "'''it's __ref(triple)'''",
    "(",
    ")",
    "'unclosed",
    "/* unclosed",
    "$$unclosed",
)
_USUAL_AND_RARE_WEIGHTS: tuple[int, int] = (94, 6)


@dataclass(frozen=True)
class _CallShape:
    call: str
    names: tuple[str, ...]
    second_arguments: tuple[str, ...]
    call_suffixes: tuple[str, ...]


_ANY_NAMES: tuple[str, ...] = (*(_NAMES * 9), *_REJECTED_NAMES)
_CALL_SHAPES: tuple[_CallShape, ...] = (
    _CallShape("__ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__source(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__seed(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__udf(", _ANY_NAMES, _NO_SECOND_ARGUMENT, ("(x)",)),
    _CallShape("__dbt_ref(", _ANY_NAMES, _DBT_SECOND_ARGUMENTS, _NO_CALL_SUFFIX),
    _CallShape("__table_fn(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _CALL_SUFFIXES),
    _CallShape("__table_fn(", _NAMES, _NO_SECOND_ARGUMENT, _CALL_SUFFIXES),
    _CallShape("___ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("x__ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
)


def _pick(*, rng: random.Random, usual: tuple[str, ...], rare: tuple[str, ...]) -> str:
    return rng.choice(rng.choices((usual, rare), weights=_USUAL_AND_RARE_WEIGHTS)[0])


@dataclass(frozen=True)
class ReferenceParity:
    """How native extraction compared with Python over one corpus; counts are native's."""

    mismatches: list[tuple[object, object, object]]
    extracted: int
    failed: int
    deferred: int
    rejected: int
    table_functions: int


def generated_reference_sqls(*, rng: random.Random, count: int) -> list[str]:
    """Return seeded SQL mixing valid, malformed, hidden and dialect-sensitive reference calls."""

    return [_generated_reference_sql(rng=rng) for _ in range(count)]


def _generated_reference_sql(*, rng: random.Random) -> str:
    return "".join(_generated_reference_call(rng=rng) for _ in range(rng.randint(1, 4)))


def _generated_reference_call(*, rng: random.Random) -> str:
    shape: _CallShape = rng.choice(_CALL_SHAPES)
    return "".join(
        (
            _pick(rng=rng, usual=_FILLERS, rare=_RISKY_FILLERS),
            shape.call,
            _pick(rng=rng, usual=shape.names, rare=_MALFORMED_NAMES),
            _pick(rng=rng, usual=shape.second_arguments, rare=_MALFORMED_SECOND_ARGUMENTS),
            ")",
            _pick(rng=rng, usual=shape.call_suffixes, rare=_MALFORMED_CALL_SUFFIXES),
        )
    )


def python_outcome(
    *, sql: str, syntax: SqlLexicalSyntax
) -> SqlReferenceScan | SqlReferenceScanFailure:
    """Return the oracle's references and rejected calls, or its error and where it points."""

    return python_reference_scan(sql=sql, syntax=syntax)


def reference_parity(*, sqls: list[str], syntax: SqlLexicalSyntax) -> ReferenceParity:
    """Compare native extraction, rejected calls and errors with Python wherever native scans."""

    native: list[SqlReferenceScan | SqlReferenceScanFailure | None] = [
        extract_native_sql_references(sql=sql, syntax=syntax) for sql in sqls
    ]
    python: list[SqlReferenceScan | SqlReferenceScanFailure] = [
        python_outcome(sql=sql, syntax=syntax) for sql in sqls
    ]
    scanned: list[bool] = [outcome is not None for outcome in native]
    extracted: list[SqlReferenceScan] = cast(
        list[SqlReferenceScan],
        list(compress(native, [isinstance(outcome, SqlReferenceScan) for outcome in native])),
    )
    return ReferenceParity(
        mismatches=mismatches(
            inputs=list(compress(sqls, scanned)),
            expected=list(compress(python, scanned)),
            actual=list(compress(native, scanned)),
        ),
        extracted=sum(not scan.invalid_calls for scan in extracted),
        failed=sum(isinstance(outcome, tuple) for outcome in native),
        deferred=native.count(None),
        rejected=sum(len(scan.invalid_calls) for scan in extracted),
        table_functions=sum(
            reference.ref_kind is SqlReferenceKind.TABLE_FUNCTION
            for reference in chain.from_iterable(map(attrgetter("references"), extracted))
        ),
    )


_LOCATED_ERROR_PATTERN: re.Pattern[str] = re.compile(r"[^:]+:\d+:\d+: ")
_FILE_HEADERS: tuple[str, ...] = (
    'MODEL (description "Orders");\n\n',
    'MODEL (\n  description "Orders",\n);\n-- notes\n\n',
    'MODEL (description "Ordres é");\n/* commentaire */\n',
    'MODEL (description "Orders over 12\\" boxes, by customer\'s totals");\n\n',
)


def generated_reference_files(*, rng: random.Random, count: int) -> list[tuple[str, str]]:
    """Return seeded authored files as `(relative path, SQL body)` pairs."""

    return [
        (f"models/area_{index % 7}/orders_{index}.sql", body)
        for index, body in enumerate(generated_reference_sqls(rng=rng, count=count))
    ]


def reported_reference_outcomes(
    *,
    files: list[tuple[str, str]],
    syntax: SqlLexicalSyntax,
    engine: CompilerEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> list[object]:
    """Extract each file's body under `engine`, keeping its references, diagnostics and error."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    return [
        _reported_reference_outcome(
            origin=SqlReferenceOrigin(
                file_path=Path("/project") / relative_path,
                relative_path=Path(relative_path),
                contents=_FILE_HEADERS[index % len(_FILE_HEADERS)] + body,
                resource_type=CompiledResourceType.MODEL,
                resource_name=Path(relative_path).stem,
                source_map=source_map_at(body_start=len(_FILE_HEADERS[index % len(_FILE_HEADERS)])),
            ),
            sql=body,
            syntax=syntax,
        )
        for index, (relative_path, body) in enumerate(files)
    ]


def _reported_reference_outcome(
    *, origin: SqlReferenceOrigin, sql: str, syntax: SqlLexicalSyntax
) -> tuple[tuple[CompileSqlReference, ...], tuple[CompilerDiagnostic, ...], str, str | None]:
    references: tuple[CompileSqlReference, ...] = ()
    with collect_compile_diagnostics() as collected:
        try:
            references = extract_sql_references(sql=sql, syntax=syntax, origin=origin)
        except CompileInputError as error:
            return (references, tuple(collected.diagnostics), str(error), error.code)
    return (references, tuple(collected.diagnostics), "", None)


def located_error_count(*, outcomes: list[object]) -> int:
    """Count the scan errors that carry an authored line and column."""

    errors: list[str] = list(map(itemgetter(2), cast(list[tuple[object, object, str]], outcomes)))
    return sum(bool(_LOCATED_ERROR_PATTERN.match(error)) for error in errors)


def located_diagnostic_count(*, outcomes: list[object]) -> int:
    """Count the reported diagnostics that carry an authored location."""

    diagnostics: list[tuple[CompilerDiagnostic, ...]] = list(
        map(itemgetter(1), cast(list[tuple[object, tuple[CompilerDiagnostic, ...]]], outcomes))
    )
    return sum(diagnostic.location is not None for diagnostic in chain.from_iterable(diagnostics))


def python_scan_not_expected(**_: object) -> SqlReferenceScan | SqlReferenceScanFailure:
    """A replacement for the Python scanner that fails the test when it is called."""

    raise AssertionError("the Python reference scanner ran")


def source_map_at(
    *, body_start: int, passes: tuple[tuple[ExpansionSpan, ...], ...] = ()
) -> SqlReferenceSourceMap:
    """Return a source map whose authored body starts at `body_start` in its file."""

    return SqlReferenceSourceMap(body_start=lambda: body_start, passes=passes)
