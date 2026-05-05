from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import FunctionArgument
from sqlbuild.compiler.compile.types import FunctionLanguage
from tests.unit.src.sqlbuild.adapter.base._test_types import (
    BaseAdapterPythonFunctionSupportTestCase,
)


class ConcreteBaseAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        del connection


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterPythonFunctionSupportTestCase(
            description="raises clear error for Python UDFs by default",
            expected_error_fragment="does not support Python UDFs",
        )
    ],
    ids=["raises clear error for Python UDFs by default"],
)
def test_given_python_function_when_rendering_with_base_adapter_then_raises_clear_error(
    test_case: BaseAdapterPythonFunctionSupportTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    with pytest.raises(NotImplementedError) as exc_info:
        adapter.render_create_function(
            target="main.is_positive_int",
            arguments=(FunctionArgument(name="a_string", type="VARCHAR"),),
            returns="BOOLEAN",
            body_sql="def main(a_string): return True",
            language=FunctionLanguage.PYTHON,
            runtime_version="3.11",
            entry_point="main",
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
