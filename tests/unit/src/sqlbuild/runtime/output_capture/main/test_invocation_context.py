"""Opaque subprocess invocation-context validation tests."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from sqlbuild.runtime.output_capture.constants import INVOCATION_CONTEXT_ENV
from sqlbuild.runtime.output_capture.exceptions import OutputCaptureInputError
from sqlbuild.runtime.output_capture.main.invocation_context import (
    invocation_context_from_environment,
)
from tests.unit.src.sqlbuild.runtime.output_capture.main._test_types import (
    InvocationContextTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        InvocationContextTestCase(
            description="nested integration identifiers",
            raw_value=json.dumps(
                {
                    "integration": {
                        "name": "dagster",
                        "run_id": "run-42",
                        "retry_number": 1,
                    }
                }
            ),
            expected_value={
                "integration": {
                    "name": "dagster",
                    "run_id": "run-42",
                    "retry_number": 1,
                }
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_valid_environment_context_when_loading_then_opaque_mapping_is_returned(
    test_case: InvocationContextTestCase,
) -> None:
    result: Mapping[str, object] = invocation_context_from_environment(
        environment={INVOCATION_CONTEXT_ENV: test_case.raw_value}
    )

    assert result == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    (
        InvocationContextTestCase(
            description="malformed JSON",
            raw_value="{",
            expected_error="must contain valid JSON",
        ),
        InvocationContextTestCase(
            description="non-object JSON",
            raw_value="[]",
            expected_error="must contain a JSON object",
        ),
        InvocationContextTestCase(
            description="oversized JSON",
            raw_value=json.dumps({"value": "x" * (16 * 1024)}),
            expected_error="must not exceed 16384 bytes",
        ),
        InvocationContextTestCase(
            description="excessively nested JSON",
            raw_value='{"a":{"b":{"c":{"d":{"e":{"f":{"g":{"h":{}}}}}}}}}',
            expected_error="must not exceed 8 levels",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_environment_context_when_loading_then_clear_error_is_raised(
    test_case: InvocationContextTestCase,
) -> None:
    with pytest.raises(OutputCaptureInputError, match=str(test_case.expected_error)):
        invocation_context_from_environment(
            environment={INVOCATION_CONTEXT_ENV: test_case.raw_value}
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
