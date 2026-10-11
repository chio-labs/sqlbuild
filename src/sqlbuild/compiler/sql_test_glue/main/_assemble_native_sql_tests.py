"""Assemble compiled SQL test facts natively for the preview compiler engine."""

from __future__ import annotations

import sqlbuild._native as native_module
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.sql_test_glue._helpers.assembly import native_sql_test_assemblies
from sqlbuild.compiler.sql_test_glue.models import (
    NativeSqlTestAssembly,
    NativeSqlTestAssemblyRequest,
)
from sqlbuild.compiler.sql_test_glue.types import NativeSqlTestAssemblyRow


def assemble_native_sql_tests(*, inputs: CompileProjectInputs) -> tuple[NativeSqlTestAssembly, ...]:
    """Return one assembly per test input, with the error its assembly raises, if any."""

    rows: list[NativeSqlTestAssemblyRow] = native_module.assemble_compiled_sql_tests(
        NativeSqlTestAssemblyRequest(
            model_inputs=inputs.model_inputs,
            test_inputs=inputs.test_inputs,
            lexical_syntax=inputs.sql_lexical_syntax.native_mapping,
        )
    )
    return native_sql_test_assemblies(test_inputs=inputs.test_inputs, rows=rows)
