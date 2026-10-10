"""Assemble every SQL test natively; macro-mocked tests' model queries run the user's macros."""

from __future__ import annotations

import decimal
from collections.abc import Callable
from dataclasses import replace

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledModelSqlTestPayload,
    CompiledSqlTest,
    CompileModelSqlTestInputPayload,
    CompileProjectInputs,
    CompileSqlTestInput,
)
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.sql_test_glue.constants import (
    SQL_TEST_DECIMAL_OVERFLOW,
    SQL_TEST_EXTENSION_CALLBACK,
    SQL_TEST_INPUT_FAILURE,
)
from sqlbuild.compiler.sql_test_glue.main._assemble_native_sql_tests import (
    assemble_native_sql_tests,
)
from sqlbuild.compiler.sql_test_glue.models import NativeSqlTestAssembly


def assemble_sql_tests_by_engine(
    *,
    inputs: CompileProjectInputs,
    macro_mock_queries: Callable[[CompileSqlTestInput], dict[str, str]],
) -> tuple[CompiledSqlTest, ...]:
    """Assemble every SQL test natively; a test mocking macros re-expands each model's query
    with the user's macros, and errors raise in Python's assembly order."""

    native: tuple[NativeSqlTestAssembly, ...] = assemble_native_sql_tests(inputs=inputs)
    tests: list[CompiledSqlTest] = []
    for test_input, assembly in zip(inputs.test_inputs, native, strict=True):
        if assembly.test is None:
            message: str = assembly.failure.message if assembly.failure is not None else ""
            if assembly.failure is not None and assembly.failure.kind == SQL_TEST_INPUT_FAILURE:
                raise CompileInputError(message)
            raise _native.NativeCompilerError(message)
        for key, diagnostic in assembly.diagnostics:
            report_compile_diagnostic(key=key, diagnostic=diagnostic)
        test: CompiledSqlTest = assembly.test
        payload: object = test_input.payload
        if isinstance(payload, CompileModelSqlTestInputPayload) and payload.macro_mocks:
            report_native_fallback(
                site=NativeFallbackSite.SQL_TEST_MACRO_MOCK_QUERIES,
                kind=SQL_TEST_EXTENSION_CALLBACK,
            )
            test = _with_model_queries(test=test, queries=macro_mock_queries(test_input))
        if assembly.failure is not None and assembly.failure.kind == SQL_TEST_DECIMAL_OVERFLOW:
            raise decimal.Overflow([decimal.Overflow])
        tests.append(test)
    return tuple(tests)


def _with_model_queries(*, test: CompiledSqlTest, queries: dict[str, str]) -> CompiledSqlTest:
    payload: object = test.payload
    if not isinstance(payload, CompiledModelSqlTestPayload):
        return test
    return replace(test, payload=replace(payload, model_query_overrides=queries))
