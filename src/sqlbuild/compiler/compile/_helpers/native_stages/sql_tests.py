"""Hand compiled SQL test assembly to its native stage when enabled."""

from __future__ import annotations

from collections.abc import Callable

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


def assemble_sql_tests_by_engine(
    *,
    inputs: CompileProjectInputs,
    assemble_python_test: Callable[[CompileSqlTestInput], CompiledSqlTest],
) -> tuple[CompiledSqlTest, ...]:
    """Assemble every SQL test natively, or each test in Python where native defers."""

    if native_stage_enabled(NativeStage.SQL_TEST_GLUE):
        native_tests: tuple[CompiledSqlTest, ...] | None = assemble_native_sql_tests(inputs=inputs)
        if native_tests is not None:
            report_native_answer(
                stage=NativeStage.SQL_TEST_GLUE, kind="sql_test_assemblies", units=len(native_tests)
            )
            return native_tests
        report_native_fallback(site=NativeFallbackSite.SQL_TEST_ASSEMBLY)
    return tuple(assemble_python_test(test_input) for test_input in inputs.test_inputs)
