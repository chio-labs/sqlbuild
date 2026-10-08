"""Native boundary for SQL-test extraction before and after expansion, under adapter rules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.constants import SQL_TEST_CTE_SCAN_ALGORITHM
from sqlbuild.compiler.compile.exceptions import (
    CompileInputError,
    NativeSqlTestResponseError,
    SqlTestExtractionError,
)
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestCtes,
    CompileModelSqlTestCtes,
    CompileSqlTestCte,
    CompileSqlTestCtes,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


class _NativeSqlTestModule(Protocol):
    def extract_sql_tests_json(self, request_json: str) -> str: ...


_DIRECT_KIND: str = "direct"
_SYNTAX_FIELDS: dict[str, str] = {
    "backslash_escape_quotes": "backslashEscapeQuotes",
    "escape_string_prefix": "escapeStringPrefix",
    "raw_string_prefix": "rawStringPrefix",
    "triple_quoted_strings": "tripleQuotedStrings",
    "nested_block_comments": "nestedBlockComments",
    "line_comment_prefixes": "lineCommentPrefixes",
}
_MODEL_KIND: str = "model"
_PAIR_LENGTH: int = 2
_AUTHORED_CTE_LENGTH: int = 3


def extract_expanded_sql_tests(
    *,
    tests: tuple[tuple[str, str, SqlTestMode], ...],
    syntax: SqlLexicalSyntax,
    scan_cache: SqlTestScanCache | None = None,
) -> tuple[CompileSqlTestCtes, ...]:
    """Extract expanded tests natively, reusing whole stored results of unchanged files."""

    store: SqlTestScanCache = scan_cache or SqlTestScanCache(cache_dir=None)
    indexes_by_file: dict[str, list[int]] = {}
    for index, (_sql, file_label, _mode) in enumerate(tests):
        indexes_by_file.setdefault(file_label, []).append(index)
    results: list[CompileSqlTestCtes | None] = [None] * len(tests)
    parts_by_file: dict[str, list[str]] = {}
    for file_label, indexes in indexes_by_file.items():
        parts: list[str] = [file_label]
        for index in indexes:
            parts.extend((tests[index][0], tests[index][2].value))
        modes: tuple[SqlTestMode, ...] = tuple(tests[index][2] for index in indexes)
        stored: tuple[CompileSqlTestCtes, ...] | None = store.read(
            algorithm=SQL_TEST_CTE_SCAN_ALGORITHM,
            syntax=syntax,
            parts=parts,
            decode=_stored_file_tests(modes=modes),
        )
        if stored is None:
            parts_by_file[file_label] = parts
            continue
        for index, test_ctes in zip(indexes, stored, strict=True):
            results[index] = test_ctes
    missing: list[int] = []
    for file_label in parts_by_file:
        missing.extend(indexes_by_file[file_label])
    missing.sort()
    if missing:
        try:
            items: list[object] = _native_batch(
                tests=[
                    {
                        "sql": tests[index][0],
                        "fileLabel": tests[index][1],
                        "mode": tests[index][2].value,
                        "raw": False,
                    }
                    for index in missing
                ],
                syntax=syntax,
            )
        except SqlTestExtractionError as error:
            error.test_index = missing[error.test_index]
            raise
        items_by_index: dict[int, object] = dict(zip(missing, items, strict=True))
        for file_label, parts in parts_by_file.items():
            file_items: list[object] = [
                items_by_index[index] for index in indexes_by_file[file_label]
            ]
            for index, item in zip(indexes_by_file[file_label], file_items, strict=True):
                results[index] = _test_ctes_from_native(item)
            store.write(
                algorithm=SQL_TEST_CTE_SCAN_ALGORITHM,
                syntax=syntax,
                parts=parts,
                value=orjson.dumps(file_items),
            )
    return tuple(result for result in results if result is not None)


def _stored_file_tests(
    *, modes: tuple[SqlTestMode, ...]
) -> Callable[[bytes], tuple[CompileSqlTestCtes, ...] | None]:
    """Decode one file's stored tests, rejecting anything that is not their exact shape."""

    def decode(value: bytes) -> tuple[CompileSqlTestCtes, ...] | None:
        try:
            items: object = orjson.loads(value)
            if not isinstance(items, list) or len(cast(list[object], items)) != len(modes):
                return None
            decoded: tuple[CompileSqlTestCtes, ...] = tuple(
                _test_ctes_from_native(item) for item in cast(list[object], items)
            )
        except (orjson.JSONDecodeError, CompileInputError):
            return None
        if any(test_ctes.mode is not mode for test_ctes, mode in zip(decoded, modes, strict=True)):
            return None
        return decoded

    return decode


def extract_unexpanded_sql_test(
    *, sql: str, file_label: str, mode: SqlTestMode, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlTestCtes, bool]:
    """Extract a direct-logic test before expansion; also report whether it has P012 calls."""

    return _extract_natively(tests=((sql, file_label, mode, True),), syntax=syntax)[0]


def authored_sql_test_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> tuple[tuple[str, int, str], ...]:
    """Read an authored block's CTEs with body offsets; only a CTE-name error is raised."""

    return authored_sql_test_cte_batch(tests=((sql, file_label),), syntax=syntax)[0]


def authored_sql_test_cte_batch(
    *, tests: tuple[tuple[str, str], ...], syntax: SqlLexicalSyntax
) -> tuple[tuple[tuple[str, int, str], ...], ...]:
    """Read many authored blocks at once; a CTE-name error names its block by `test_index`."""

    if not tests:
        return ()
    results: list[object] = _native_batch(
        tests=[
            {"sql": sql, "fileLabel": file_label, "mode": "model", "authored": True}
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


def _extract_natively(
    *, tests: tuple[tuple[str, str, SqlTestMode, bool], ...], syntax: SqlLexicalSyntax
) -> tuple[tuple[CompileSqlTestCtes, bool], ...]:
    results: list[object] = _native_batch(
        tests=[
            {"sql": sql, "fileLabel": file_label, "mode": mode.value, "raw": raw}
            for sql, file_label, mode, raw in tests
        ],
        syntax=syntax,
    )
    return tuple((_test_ctes_from_native(item), _invalid_calls(item)) for item in results)


def _invalid_calls(item: object) -> bool:
    return isinstance(item, dict) and cast(dict[str, object], item).get("invalidCalls") is True


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


def _test_ctes_from_native(value: object) -> CompileSqlTestCtes:
    if not isinstance(value, dict):
        raise CompileInputError("native SQL test extraction returned an invalid test response")
    payload: dict[str, object] = cast(dict[str, object], value)
    try:
        mode: SqlTestMode = SqlTestMode(_required_string(value=payload, key="mode"))
        kind: str = _required_string(value=payload, key="kind")
        if kind == _DIRECT_KIND:
            return CompileSqlTestCtes(
                mode=mode,
                payload=CompileDirectLogicSqlTestCtes(
                    mode=mode,
                    helper_ctes=_ctes(payload.get("helpers")),
                    actual_cte=_cte(payload.get("actual")),
                    expected_cte=_cte(payload.get("expected")),
                ),
            )
        if kind != _MODEL_KIND or mode is not SqlTestMode.MODEL:
            raise NativeSqlTestResponseError("native SQL test extraction returned an invalid kind")
        return CompileSqlTestCtes(
            mode=mode,
            payload=CompileModelSqlTestCtes(
                authored_ctes=_ctes(payload.get("authored")),
                macro_mocks=dict(_string_pairs(payload.get("macroMocks"))),
                mock_model_names=_strings(payload.get("mockModels")),
                mock_source_names=_strings(payload.get("mockSources")),
                mock_seed_names=_strings(payload.get("mockSeeds")),
                mock_dbt_ref_names=_strings(payload.get("mockDbtRefs")),
                mock_table_function_names=_strings(payload.get("mockTableFunctions")),
                expected_ctes=_ctes(payload.get("expected")),
                expected_model_names=_strings(payload.get("expectedModels")),
                assertion_ctes=_ctes(payload.get("assertions")),
                assertion_names=_strings(payload.get("assertionNames")),
            ),
        )
    except (KeyError, TypeError, ValueError, NativeSqlTestResponseError):
        raise CompileInputError(
            "native SQL test extraction returned an invalid test response"
        ) from None


def _required_string(*, value: dict[str, object], key: str) -> str:
    item: object = value[key]
    if not isinstance(item, str):
        raise NativeSqlTestResponseError("native SQL test extraction expected a string")
    return item


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise NativeSqlTestResponseError("native SQL test extraction expected a string list")
    return tuple(cast(list[str], value))


def _cte(value: object) -> CompileSqlTestCte:
    if (
        not isinstance(value, list)
        or len(value) != _PAIR_LENGTH
        or not isinstance(value[0], str)
        or not isinstance(value[1], str)
    ):
        raise NativeSqlTestResponseError("native SQL test extraction expected one CTE pair")
    return CompileSqlTestCte(name=value[0], sql_body=value[1])


def _ctes(value: object) -> tuple[CompileSqlTestCte, ...]:
    if not isinstance(value, list):
        raise NativeSqlTestResponseError("native SQL test extraction expected a CTE list")
    return tuple(_cte(item) for item in value)


def _string_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise NativeSqlTestResponseError("native SQL test extraction expected a pair list")
    pairs: list[tuple[str, str]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != _PAIR_LENGTH
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise NativeSqlTestResponseError("native SQL test extraction expected string pairs")
        pairs.append((item[0], item[1]))
    return tuple(pairs)
