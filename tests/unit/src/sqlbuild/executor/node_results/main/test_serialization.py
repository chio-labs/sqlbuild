"""Tests for node result JSON serialization."""

from __future__ import annotations

import pytest

from sqlbuild.executor.node_results.helpers.serialization import encode_json_b64
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from tests.unit.src.sqlbuild.executor.node_results.main._test_types import (
    NodeResultSerializationErrorTestCase,
    NodeResultSerializationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeResultSerializationTestCase(
            description="encodes JSON payload deterministically",
            value={"value": 42},
            expected_encoded="eyJ2YWx1ZSI6NDJ9",
        )
    ],
    ids=["encodes JSON payload deterministically"],
)
def test_given_json_value_when_encoding_result_storage_then_returns_base64_json(
    test_case: NodeResultSerializationTestCase,
) -> None:
    encoded: str = encode_json_b64(
        test_case.value,
        label="payload",
        node_name="produce_result",
    )

    assert encoded == test_case.expected_encoded


@pytest.mark.parametrize(
    "test_case",
    [
        NodeResultSerializationErrorTestCase(
            description="rejects non JSON serializable payload",
            value={"items": {"a", "b"}},
            expected_error_fragment="non-JSON-serializable payload",
        )
    ],
    ids=["rejects non JSON serializable payload"],
)
def test_given_non_json_value_when_encoding_result_storage_then_raises_input_error(
    test_case: NodeResultSerializationErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        encode_json_b64(
            test_case.value,
            label="payload",
            node_name="produce_result",
        )
