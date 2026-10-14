"""Generated authored SQL and attached audits for the native attachment parity tests."""

from __future__ import annotations

import json
import random
import re
from typing import Any

import sqlbuild._native as _native
from sqlbuild._native import find_macro_call_names, scan_sql_reference_calls
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    SqlReferenceScan,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_SQL_PIECES: tuple[str, ...] = (
    "SELECT * FROM t WHERE ",
    "@column",
    "@'column'",
    "@values",
    "@'values'",
    "@limit_rows",
    "@@column",
    "@@@window",
    "@tidy(@column)",
    "@column (x)",
    " AND ",
    "'@column'",
    "@column\u00e9",
    "@column\u00a0(",
    "@values\u2003(",
    "@'values'\u3000",
    "\n",
)
_MACRO_PIECES: tuple[str, ...] = (
    "a",
    "@m(1)",
    "@m (1)",
    "@ab (1)",
    "@ab cd(1)",
    "@enum('Status', 'PAID')",
    "@const(@m(1))",
    "@var('x')",
    '@param("p")',
    "@@region",
    "@m$x(1)",
    '@"m"(1)',
    "@\u00e9t\u00e9(1)",
    "@m\u00a0(1)",
    "@mm\u3000(1)",
    "@mm\x1c(1)",
    "'@m(1)'",
    "-- @m(1)\n",
    "/* @m(1) */",
    "$$@m(1)$$",
    "$t$@m(1)$t$",
    "`@m(1)`",
    '"@m(1)"',
    "x@m(1)",
    "@m(@n(1))",
    "@_m(1)",
    "@1m(1)",
    "@\u216b(1)",
)
_REFERENCE_PIECES: tuple[str, ...] = (
    "a",
    '__udf("order_label")(a)',
    '__table_fn("order_rows")(1)',
    '__ref("orders")',
    '__source("events", "orders")',
    '__source("events")',
    '__dbt_ref("shop", "orders")',
    '__dbt_ref("orders")',
    "__dbt_ref(orders)",
    "__udf('order_label')",
    '__udf("order_label", 1)',
    "__udf(order_label)",
    '__udf("")',
    '__udf(  "order_label" )',
    '__table_fn("order_rows")',
    '__table_fn("order_rows")\u00a0(1)',
    '__table_fn("order_rows") (1)',
    '__UDF("order_label")',
    '__udf ("order_label")',
    'x__udf("order_label")(a)',
    "'__udf(\"order_label\")'",
    '-- __udf("order_label")\n',
    '# __udf("order_label")\n',
    '// __udf("order_label")\n',
    '/* /* __udf("order_label") */ */',
    "'it''s'",
    '$$__udf("order_label")$$',
    '`__udf("order_label")`',
)
_LOGIC_REFERENCE_KINDS: frozenset[str] = frozenset({"udf", "table_fn"})
BODY_CALL_SYNTAXES: dict[str, SqlLexicalSyntax] = {
    "generic": SqlLexicalSyntax(),
    "duckdb": SqlLexicalSyntax(escape_string_prefix=True, nested_block_comments=True),
    "bigquery": SqlLexicalSyntax(
        backslash_escape_quotes=frozenset({"'", '"', "`"}),
        triple_quoted_strings=True,
        line_comment_prefixes=frozenset({"--", "#"}),
    ),
    "snowflake": SqlLexicalSyntax(
        backslash_escape_quotes=frozenset({"'"}), line_comment_prefixes=frozenset({"--", "//"})
    ),
}


def generated_macro_body(*, rng: random.Random) -> str:
    """Return one helper body mixing macro calls and macro-like text."""

    pieces: list[str] = [rng.choice(_MACRO_PIECES) for _ in range(rng.randint(1, 3))]
    return "SELECT " + " + ".join(pieces) + " AS a"


def generated_reference_body(*, rng: random.Random) -> str:
    """Return one helper body mixing valid, malformed and hidden reference calls."""

    pieces: list[str] = [rng.choice(_REFERENCE_PIECES) for _ in range(rng.randint(1, 3))]
    return "SELECT " + " + ".join(pieces) + "\n AS a"


def python_macro_outcome(*, body: str) -> str:
    """Whether expansion's macro scanner finds a call in `body`, or that it raises."""

    try:
        return f"calls macros {bool(find_macro_call_names(body))}"
    except CompileInputError:
        return "unscannable"


def macro_scannable(body: str) -> bool:
    """Whether expansion's macro scanner reads `body` without raising."""

    return python_macro_outcome(body=body) != "unscannable"


def native_macro_outcome(*, body: str) -> str:
    """Whether the raw extractor rejects a macro-test helper `body` for calling macros."""

    response: dict[str, Any] = _raw_extraction(
        sql=(
            f"WITH h AS ({body}), __macro_actual__ AS (SELECT @m(1) AS a), "
            "__macro_expected__ AS (SELECT 1 AS a)"
        ),
        mode=SqlTestMode.MACRO,
        syntax=SqlLexicalSyntax(),
    )
    message: str = str(response.get("error", {}).get("message", ""))
    return f"calls macros {'must not call macros' in message}"


def python_reference_outcome(*, body: str, syntax: SqlLexicalSyntax) -> str:
    """Python's first `__udf`/`__table_fn` kind in `body`, or whether it has P012 calls."""

    try:
        scan: SqlReferenceScan = scan_sql_reference_calls(sql=body, syntax=syntax)
    except CompileInputError as error:
        return f"error: {error}"
    kinds: list[str] = [str(reference.ref_kind) for reference in scan.references]
    kind: str | None = next(filter(_LOGIC_REFERENCE_KINDS.__contains__, kinds), None)
    return (kind and f"calls {kind}") or f"malformed calls {bool(scan.invalid_calls)}"


def native_reference_outcome(*, body: str, syntax: SqlLexicalSyntax) -> str:
    """The raw extractor's reading of a UDF-test helper `body`, as `python_reference_outcome`."""

    response: dict[str, Any] = _raw_extraction(
        sql=(
            f"WITH h AS ({body}), __udf_actual__ AS (SELECT 1 AS a), "
            "__udf_expected__ AS (SELECT 1 AS a)"
        ),
        mode=SqlTestMode.UDF,
        syntax=syntax,
    )
    message: str = str(response.get("error", {}).get("message", ""))
    called: re.Match[str] | None = re.search(r"must not call (\w+);", message)
    invalid_calls: object = response.get("tests", [{}])[0].get("invalidCalls", False)
    return (
        (called and f"calls {called.group(1)}")
        or (message and f"error: {message}")
        or f"malformed calls {invalid_calls}"
    )


def _raw_extraction(*, sql: str, mode: SqlTestMode, syntax: SqlLexicalSyntax) -> dict[str, Any]:
    """The native extractor's response for one test before expansion."""

    request: dict[str, object] = {
        "syntax": {_SYNTAX_FIELDS[key]: value for key, value in syntax.native_mapping.items()},
        "tests": [
            {"sql": sql, "fileLabel": "tests/unit/test_logic.sql", "mode": mode.value, "raw": True}
        ],
    }
    return json.loads(_native.extract_sql_tests_json(json.dumps(request)))


_SYNTAX_FIELDS: dict[str, str] = {
    "backslash_escape_quotes": "backslashEscapeQuotes",
    "escape_string_prefix": "escapeStringPrefix",
    "raw_string_prefix": "rawStringPrefix",
    "triple_quoted_strings": "tripleQuotedStrings",
    "nested_block_comments": "nestedBlockComments",
    "line_comment_prefixes": "lineCommentPrefixes",
}
