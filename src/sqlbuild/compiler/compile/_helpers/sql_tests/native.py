"""Native boundary for SQL-test extraction before and after expansion, under adapter rules."""

from __future__ import annotations

from typing import Protocol, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import (
    CompileInputError,
    SqlTestExtractionError,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


class _NativeSqlTestModule(Protocol):
    def extract_sql_tests_json(self, request_json: str) -> str: ...


_SYNTAX_FIELDS: dict[str, str] = {
    "backslash_escape_quotes": "backslashEscapeQuotes",
    "escape_string_prefix": "escapeStringPrefix",
    "raw_string_prefix": "rawStringPrefix",
    "triple_quoted_strings": "tripleQuotedStrings",
    "nested_block_comments": "nestedBlockComments",
    "line_comment_prefixes": "lineCommentPrefixes",
}
_AUTHORED_CTE_LENGTH: int = 3


def authored_sql_test_cte_batch(
    *, tests: tuple[tuple[str, str], ...], syntax: SqlLexicalSyntax, scenarios: bool = False
) -> tuple[tuple[tuple[str, int, str], ...], ...]:
    """Read many authored blocks or scenarios at once; a CTE error names one by `test_index`."""

    if not tests:
        return ()
    results: list[object] = _native_batch(
        tests=[
            {
                "sql": sql,
                "fileLabel": file_label,
                "mode": "model",
                "authored": True,
                "scenario": scenarios,
            }
            for sql, file_label in tests
        ],
        syntax=syntax,
    )
    return tuple(_authored_ctes(item) for item in results)


def _authored_ctes(item: object) -> tuple[tuple[str, int, str], ...]:
    ctes: object = cast(dict[str, object], item).get("ctes") if isinstance(item, dict) else None
    if not isinstance(ctes, list):
        raise CompileInputError("native SQL test extraction returned an invalid CTE response")
    return tuple(_authored_cte(value) for value in ctes)


def _authored_cte(value: object) -> tuple[str, int, str]:
    if not (
        isinstance(value, list)
        and len(value) == _AUTHORED_CTE_LENGTH
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and isinstance(value[2], str)
    ):
        raise CompileInputError("native SQL test extraction returned an invalid CTE")
    return value[0], value[1], value[2]


def _native_batch(*, tests: list[dict[str, object]], syntax: SqlLexicalSyntax) -> list[object]:
    native_syntax: dict[str, object] = syntax.native_mapping
    request_json: str = orjson.dumps(
        {
            "syntax": {_SYNTAX_FIELDS[key]: value for key, value in native_syntax.items()},
            "tests": tests,
        }
    ).decode()
    try:
        response: object = orjson.loads(
            cast(_NativeSqlTestModule, _native).extract_sql_tests_json(request_json)
        )
    except ValueError as error:
        raise CompileInputError(str(error)) from None
    if isinstance(response, dict) and isinstance(response.get("error"), dict):
        raise _extraction_error(cast(dict[str, object], response["error"]))
    results: object = response.get("tests") if isinstance(response, dict) else None
    if not isinstance(results, list) or len(results) != len(tests):
        raise CompileInputError("native SQL test extraction returned an invalid batch response")
    return cast(list[object], results)


def _extraction_error(error: dict[str, object]) -> SqlTestExtractionError:
    message: object = error.get("message")
    help_text: object = error.get("help")
    index: object = error.get("index")
    token: object = error.get("token")
    token_offset: object = error.get("tokenOffset")
    return SqlTestExtractionError(
        message if isinstance(message, str) else "native SQL test extraction failed",
        help=help_text if isinstance(help_text, str) else None,
        test_index=index if isinstance(index, int) else 0,
        token=token if isinstance(token, str) else None,
        token_offset=token_offset if isinstance(token_offset, int) else None,
    )
