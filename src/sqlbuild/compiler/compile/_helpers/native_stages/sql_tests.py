"""Hand compiled SQL test assembly to its native stage when enabled."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile.models import (
    CompiledSqlTest,
    CompileProjectInputs,
    CompileSqlTestInput,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.sql_test_glue.main._assemble_native_sql_tests import (
    assemble_native_sql_tests,
)
from sqlbuild.compiler.sql_test_glue.models import NativeSqlTestAssembly


def assemble_sql_tests_by_engine(
    *,
    inputs: CompileProjectInputs,
    assemble_python_test: Callable[[CompileSqlTestInput], CompiledSqlTest],
) -> tuple[CompiledSqlTest, ...]:
    """Assemble every SQL test natively, or each test in Python where native defers."""

    if not native_stage_enabled(NativeStage.SQL_TEST_GLUE):
        return tuple(assemble_python_test(test_input) for test_input in inputs.test_inputs)
    native: tuple[NativeSqlTestAssembly | None, ...] = assemble_native_sql_tests(inputs=inputs)
    tests: list[CompiledSqlTest] = []
    for test_input, assembly in zip(inputs.test_inputs, native, strict=True):
        if assembly is None:
            report_native_fallback(site=NativeFallbackSite.SQL_TEST_ASSEMBLY)
            tests.append(assemble_python_test(test_input))
            continue
        for key, diagnostic in assembly.diagnostics:
            report_compile_diagnostic(key=key, diagnostic=diagnostic)
        report_native_answer(stage=NativeStage.SQL_TEST_GLUE, kind="sql_test_assemblies")
        tests.append(assembly.test)
    return tuple(tests)
