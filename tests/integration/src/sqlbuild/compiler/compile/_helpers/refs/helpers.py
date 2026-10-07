"""Generated reference SQL and native-versus-Python comparison for reference extraction."""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import chain, compress
from typing import cast

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile._helpers.refs.native import extract_native_sql_references
from sqlbuild.compiler.compile._helpers.refs.references import (
    _extract_sql_references_with_python,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
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
    "'customers'",
    "products",
    "  inventory\t",
    "'commandés'",
    "orders\x1c",
    "orders /* note */",
    "-- note\norders",
)
_QUOTED_NAMES: tuple[str, ...] = (
    '"orders"',
    ' "order""s" ',
    '"a" "b"',
    '""',
    '"größe"',
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
_DBT_SECOND_ARGUMENTS: tuple[str, ...] = ("", ", products", ' , "orders"')
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


_ANY_NAMES: tuple[str, ...] = (*_NAMES, *_QUOTED_NAMES)
_CALL_SHAPES: tuple[_CallShape, ...] = (
    _CallShape("__ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__source(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__seed(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("__udf(", _ANY_NAMES, _NO_SECOND_ARGUMENT, ("(x)",)),
    _CallShape("__dbt_ref(", _ANY_NAMES, _DBT_SECOND_ARGUMENTS, _NO_CALL_SUFFIX),
    _CallShape("__table_fn(", _QUOTED_NAMES, _NO_SECOND_ARGUMENT, _CALL_SUFFIXES),
    _CallShape("__table_fn(", _QUOTED_NAMES, _NO_SECOND_ARGUMENT, _CALL_SUFFIXES),
    _CallShape("___ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
    _CallShape("x__ref(", _ANY_NAMES, _NO_SECOND_ARGUMENT, _NO_CALL_SUFFIX),
)


def _pick(*, rng: random.Random, usual: tuple[str, ...], rare: tuple[str, ...]) -> str:
    return rng.choice(rng.choices((usual, rare), weights=_USUAL_AND_RARE_WEIGHTS)[0])


@dataclass(frozen=True)
class ReferenceParity:
    """How native extraction compared with Python over one corpus."""

    mismatches: list[tuple[object, object, object]]
    extracted: int
    failed: int
    deferred: int
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


def python_outcome(*, sql: str, syntax: SqlLexicalSyntax) -> tuple[CompileSqlReference, ...] | str:
    """Return the oracle scanner's references or the message of the error it raises."""

    try:
        return _extract_sql_references_with_python(sql=sql, syntax=syntax)
    except CompileInputError as error:
        return str(error)


def reference_parity(*, sqls: list[str], syntax: SqlLexicalSyntax) -> ReferenceParity:
    """Compare native extraction with Python wherever the native scan does not defer."""

    native: list[tuple[CompileSqlReference, ...] | str | None] = [
        extract_native_sql_references(sql=sql, syntax=syntax) for sql in sqls
    ]
    python: list[tuple[CompileSqlReference, ...] | str] = [
        python_outcome(sql=sql, syntax=syntax) for sql in sqls
    ]
    scanned: list[bool] = [outcome is not None for outcome in native]
    extracted: list[tuple[CompileSqlReference, ...]] = cast(
        list[tuple[CompileSqlReference, ...]],
        list(compress(native, [isinstance(outcome, tuple) for outcome in native])),
    )
    return ReferenceParity(
        mismatches=mismatches(
            inputs=list(compress(sqls, scanned)),
            expected=list(compress(python, scanned)),
            actual=list(compress(native, scanned)),
        ),
        extracted=len(extracted),
        failed=sum(isinstance(outcome, str) for outcome in native),
        deferred=scanned.count(False),
        table_functions=sum(
            reference.ref_kind is SqlReferenceKind.TABLE_FUNCTION
            for reference in chain.from_iterable(extracted)
        ),
    )
