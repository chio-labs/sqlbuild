from unittest.mock import Mock

import pytest

from sqlbuild.compute_logs import ComputeLogStream
from sqlbuild.runtime.compute_logs.classes.binary_tee import BinaryComputeLogTee
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from tests.unit.src.sqlbuild.runtime.compute_logs.classes._test_types import (
    PartialWriteTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PartialWriteTestCase(
            description="binary partial result retains accepted prefix",
            sink_result=2,
            expected_result=2,
            expected_bytes=b"ab",
        ),
        PartialWriteTestCase(
            description="binary None result means full acceptance",
            sink_result=None,
            expected_result=6,
            expected_bytes=b"abcdef",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_binary_sink_result_when_writing_then_only_accepted_prefix_is_retained(
    test_case: PartialWriteTestCase,
) -> None:
    sink: Mock = Mock()
    sink.write.return_value = test_case.sink_result
    storage: Mock = Mock()
    tee: BinaryComputeLogTee = BinaryComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="binary_partial",
        stream=ComputeLogStream.STDOUT,
    )

    result: int = tee.write(b"abcdef")

    assert result == test_case.expected_result
    storage.append.assert_called_once_with(
        invocation_id="binary_partial",
        stream=ComputeLogStream.STDOUT,
        data=test_case.expected_bytes,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        PartialWriteTestCase(
            description="text partial result retains accepted characters encoded as UTF8",
            sink_result=2,
            expected_result=2,
            expected_bytes="Aé".encode(),
        ),
        PartialWriteTestCase(
            description="text None result means full acceptance",
            sink_result=None,
            expected_result=3,
            expected_bytes="AéB".encode(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_text_sink_result_when_writing_then_only_accepted_characters_are_retained(
    test_case: PartialWriteTestCase,
) -> None:
    sink: Mock = Mock()
    sink.encoding = "utf-8"
    sink.errors = "strict"
    sink.buffer = Mock()
    sink.write.return_value = test_case.sink_result
    storage: Mock = Mock()
    tee: TextComputeLogTee = TextComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="text_partial",
        stream=ComputeLogStream.STDOUT,
    )

    result: int = tee.write("AéB")

    assert result == test_case.expected_result
    storage.append.assert_called_once_with(
        invocation_id="text_partial",
        stream=ComputeLogStream.STDOUT,
        data=test_case.expected_bytes,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        PartialWriteTestCase(
            description="sink exception retains no bytes",
            sink_result=None,
            expected_result=0,
            expected_bytes=b"",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sink_exception_when_writing_then_exception_propagates_without_retention(
    test_case: PartialWriteTestCase,
) -> None:
    sink: Mock = Mock()
    sink.write.side_effect = OSError("controlled sink failure")
    storage: Mock = Mock()
    tee: BinaryComputeLogTee = BinaryComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="sink_exception",
        stream=ComputeLogStream.STDOUT,
    )

    with pytest.raises(OSError, match="controlled sink failure"):
        _ = tee.write(b"not retained")

    assert test_case.expected_result == 0
    assert test_case.expected_bytes == b""
    storage.append.assert_not_called()


@pytest.mark.parametrize(
    "test_case",
    (
        PartialWriteTestCase(
            description="text sink exception retains no encoded bytes",
            sink_result=None,
            expected_result=0,
            expected_bytes=b"",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_text_sink_exception_when_writing_then_exception_propagates_without_retention(
    test_case: PartialWriteTestCase,
) -> None:
    sink: Mock = Mock()
    sink.encoding = "utf-8"
    sink.errors = "strict"
    sink.buffer = Mock()
    sink.write.side_effect = OSError("controlled text sink failure")
    storage: Mock = Mock()
    tee: TextComputeLogTee = TextComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="text_sink_exception",
        stream=ComputeLogStream.STDOUT,
    )

    with pytest.raises(OSError, match="controlled text sink failure"):
        _ = tee.write("not retained")

    assert test_case.expected_result == 0
    assert test_case.expected_bytes == b""
    storage.append.assert_not_called()
