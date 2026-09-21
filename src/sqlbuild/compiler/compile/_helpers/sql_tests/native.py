"""Native batch boundary for expanded SQL-test extraction."""

from __future__ import annotations

from typing import Protocol, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError, NativeSqlTestResponseError
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestCtes,
    CompileModelSqlTestCtes,
    CompileSqlTestCte,
    CompileSqlTestCtes,
)
from sqlbuild.compiler.compile.types import SqlTestMode


class _NativeSqlTestModule(Protocol):
    def extract_sql_tests_json(self, request_json: str) -> str: ...


_DIRECT_KIND: str = "direct"
_MODEL_KIND: str = "model"
_PAIR_LENGTH: int = 2


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
