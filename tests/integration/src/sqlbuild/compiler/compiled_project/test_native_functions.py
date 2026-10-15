"""Functions attached by the native model loop and assembled into the native compiled project."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sqlbuild._native import CompileInputError
from sqlbuild.compiler.compile.types import CompiledFunctionView
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    NativeFunctionAttachmentTestCase,
    NativeFunctionErrorTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    FUNCTION_PROJECT_FILES,
    compile_function_project,
    function_summary,
)

if TYPE_CHECKING:
    from sqlbuild._native import FunctionInput


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFunctionAttachmentTestCase(
            description="scalar SQL function with templated types under the default schema",
            function_name="order_total",
            expected_summary=(
                "NativeCompiledFunction",
                "udf",
                (),
                (("amount", "DECIMAL(10, 2)"),),
                "DECIMAL(10, 2)",
                (),
                (),
                "sql",
                "udfs_eu.order_total",
                "udfs_eu.order_total",
                (None, (), ("finance",), "Order total."),
            ),
            expected_usages=(),
        ),
        NativeFunctionAttachmentTestCase(
            description="table SQL function reading a model and an enum in its own schema",
            function_name="open_orders",
            expected_summary=(
                "NativeCompiledFunction",
                "table_fn",
                ("orders",),
                (),
                "TABLE",
                (("order_id", "INTEGER"), ("status", "VARCHAR")),
                ("orders",),
                "sql",
                "reporting.open_orders",
                "reporting.open_orders",
                (None, (), (), "Open orders."),
            ),
            expected_usages=("enum:order_status",),
        ),
        NativeFunctionAttachmentTestCase(
            description="Python function fingerprinted in the default schema it does not inherit",
            function_name="score",
            expected_summary=(
                "NativeCompiledFunction",
                "udf",
                (),
                (("value", "INTEGER"),),
                "INTEGER",
                (),
                (),
                "python",
                "score",
                "udfs_eu.score",
                ("3.11", ("numpy",), ("ml",), "Score."),
            ),
            expected_usages=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_function_when_compiling_then_native_project_holds_its_attachment(
    test_case: NativeFunctionAttachmentTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, inputs = compile_function_project(
        project_dir=tmp_path, files=FUNCTION_PROJECT_FILES, monkeypatch=monkeypatch
    )

    function: CompiledFunctionView = {item.name: item for item in project.functions}[
        test_case.function_name
    ]
    function_input: FunctionInput = {item.name: item for item in inputs.sql_function_inputs}[
        test_case.function_name
    ]
    assert function_summary(function) == test_case.expected_summary
    assert type(function_input).__name__ == "NativeFunctionInput"
    assert (
        tuple(
            f"{usage.declaration.kind.value}:{usage.declaration.name}"
            for usage in function_input.declaration_usages
        )
        == test_case.expected_usages
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFunctionErrorTestCase(
            description="table function called with the wrong argument count",
            files={
                "functions/sql/customer_orders.sql": (
                    "FUNCTION (description 'Customer orders.', arguments (customer_id INTEGER),"
                    " returns table (order_id INTEGER));\nSELECT customer_id AS order_id\n"
                ),
                "models/report.sql": (
                    "MODEL (description 'Report.');\n"
                    'SELECT * FROM __table_fn("customer_orders")(1, 2)\n'
                ),
            },
            expected_message=(
                "Model file models/report.sql table function 'customer_orders' expects 1"
                " argument but received 2"
            ),
        ),
        NativeFunctionErrorTestCase(
            description="function body reading an unknown model",
            files={
                "functions/sql/lookup.sql": (
                    "FUNCTION (description 'Lookup.', returns INTEGER);\n"
                    'SELECT COUNT(*) FROM __ref("missing_orders")\n'
                ),
            },
            expected_message=(
                "SQL function file functions/sql/lookup.sql references unknown model"
                " 'missing_orders'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_function_when_compiling_then_native_attachment_rejects_it(
    test_case: NativeFunctionErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CompileInputError) as raised:
        _ = compile_function_project(
            project_dir=tmp_path,
            files={**FUNCTION_PROJECT_FILES, **test_case.files},
            monkeypatch=monkeypatch,
        )

    assert test_case.expected_message in str(raised.value)
