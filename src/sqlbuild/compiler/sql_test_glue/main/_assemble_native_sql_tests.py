"""Assemble compiled SQL test facts natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledSqlTest, CompileProjectInputs


def assemble_native_sql_tests(
    *, inputs: CompileProjectInputs
) -> tuple[CompiledSqlTest, ...] | None:
    """Return one compiled test per test input, or None where Python must assemble the tests."""

    return None
