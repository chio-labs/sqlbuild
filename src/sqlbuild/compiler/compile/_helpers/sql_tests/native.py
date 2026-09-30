"""Native batch boundary for expanded SQL-test extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import (
    SQL_TEST_FACT_CACHE_ALGORITHM,
    SQL_TEST_FACT_CACHE_NAMESPACE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError, NativeSqlTestResponseError
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestCtes,
    CompileModelSqlTestCtes,
    CompileSqlTestCte,
    CompileSqlTestCtes,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.fact_cache.classes.fact_cache_store import FactCacheStore


class _NativeSqlTestModule(Protocol):
    def extract_sql_tests_json(self, request_json: str) -> str: ...


_DIRECT_KIND: str = "direct"
_MODEL_KIND: str = "model"
_PAIR_LENGTH: int = 2


def extract_expanded_sql_tests_cached(
    *,
    tests: tuple[tuple[str, str, SqlTestMode], ...],
    cache_root: Path | None,
) -> tuple[CompileSqlTestCtes, ...]:
    """Reuse exact per-file extraction facts and extract only tests of changed files natively."""

    with FactCacheStore(
        root=cache_root,
        namespace=SQL_TEST_FACT_CACHE_NAMESPACE,
        algorithm=SQL_TEST_FACT_CACHE_ALGORITHM,
    ) as fact_cache:
        if not fact_cache.enabled:
            return extract_expanded_sql_tests(tests)
        indexes_by_file: dict[str, list[int]] = {}
        for index, (_sql, file_label, _mode) in enumerate(tests):
            indexes_by_file.setdefault(file_label, []).append(index)
        keys_by_file: dict[str, str] = {
            file_label: fact_cache.key(
                file_label, *_file_test_key_parts(tests=tests, indexes=indexes)
            )
            for file_label, indexes in indexes_by_file.items()
        }
        cached: dict[str, object] = fact_cache.read_many(tuple(keys_by_file.items()))
        results: list[CompileSqlTestCtes | None] = [None] * len(tests)
        missing_files: list[str] = []
        for file_label, indexes in indexes_by_file.items():
            file_results: tuple[CompileSqlTestCtes, ...] | None = _cached_file_tests(
                value=cached.get(keys_by_file[file_label]),
                modes=tuple(tests[index][2] for index in indexes),
            )
            if file_results is None:
                missing_files.append(file_label)
                continue
            for index, test_ctes in zip(indexes, file_results, strict=True):
                results[index] = test_ctes
        missing_indexes: list[int] = []
        for file_label in missing_files:
            missing_indexes.extend(indexes_by_file[file_label])
        if missing_indexes:
            extracted: tuple[CompileSqlTestCtes, ...] = extract_expanded_sql_tests(
                tuple(tests[index] for index in missing_indexes)
            )
            for index, test_ctes in zip(missing_indexes, extracted, strict=True):
                results[index] = test_ctes
            for file_label in missing_files:
                fact_cache.stage(
                    key=keys_by_file[file_label],
                    slot=file_label,
                    value=tuple(results[index] for index in indexes_by_file[file_label]),
                )
        return tuple(result for result in results if result is not None)


def _file_test_key_parts(
    *, tests: tuple[tuple[str, str, SqlTestMode], ...], indexes: list[int]
) -> list[str]:
    parts: list[str] = []
    for index in indexes:
        sql, _file_label, mode = tests[index]
        parts.extend((sql, mode.value))
    return parts


def _cached_file_tests(
    *, value: object, modes: tuple[SqlTestMode, ...]
) -> tuple[CompileSqlTestCtes, ...] | None:
    if not isinstance(value, tuple) or len(value) != len(modes):
        return None
    for test_ctes, mode in zip(value, modes, strict=True):
        if not isinstance(test_ctes, CompileSqlTestCtes) or test_ctes.mode is not mode:
            return None
    return cast(tuple[CompileSqlTestCtes, ...], value)


def extract_expanded_sql_tests(
    tests: tuple[tuple[str, str, SqlTestMode], ...],
) -> tuple[CompileSqlTestCtes, ...]:
    """Extract and classify expanded tests in one authoritative native call."""

    request_json: str = orjson.dumps(
        {
            "tests": [
                {"sql": sql, "fileLabel": file_label, "mode": mode.value}
                for sql, file_label, mode in tests
            ]
        }
    ).decode()
    try:
        response: object = orjson.loads(
            cast(_NativeSqlTestModule, _native).extract_sql_tests_json(request_json)
        )
    except ValueError as error:
        raise CompileInputError(str(error)) from None
    if not isinstance(response, list) or len(response) != len(tests):
        raise CompileInputError("native SQL test extraction returned an invalid batch response")
    return tuple(_test_ctes_from_native(item) for item in response)


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
