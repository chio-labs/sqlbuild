"""SQL and Python function headers attach identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    FunctionHeaderParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    function_outcome,
    generated_function_header,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionHeaderParityTestCase(
            description="target schema, Python functions inherit the default namespace",
            seed=20261008,
            count=1500,
            target_schema="prod",
            inherit_default_namespace=True,
            expected_minimum_attached=150,
            expected_minimum_python_errors=800,
        ),
        FunctionHeaderParityTestCase(
            description="no target schema, Python functions keep their own namespace",
            seed=20261009,
            count=1500,
            target_schema=None,
            inherit_default_namespace=False,
            expected_minimum_attached=150,
            expected_minimum_python_errors=800,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_function_headers_when_attaching_with_preview_then_python_matches(
    test_case: FunctionHeaderParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    headers: list[tuple[dict[str, object], bool]] = [
        (generated_function_header(rng=rng, python=python), python)
        for python in rng.choices((False, True), k=test_case.count)
    ]

    python: list[str] = [
        function_outcome(
            header_values=header,
            python=python_function,
            test_case=test_case,
            engine=CompilerEngine.PYTHON,
            monkeypatch=monkeypatch,
        )
        for header, python_function in headers
    ]
    preview: list[str] = [
        function_outcome(
            header_values=header,
            python=python_function,
            test_case=test_case,
            engine=CompilerEngine.NATIVE_PREVIEW,
            monkeypatch=monkeypatch,
        )
        for header, python_function in headers
    ]

    assert (
        mismatches(inputs=[*headers], expected=[*python], actual=[*preview]),
        sum(not item.startswith("error: ") for item in python)
        >= test_case.expected_minimum_attached,
        sum(item.startswith("error: ") for item in python)
        >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
