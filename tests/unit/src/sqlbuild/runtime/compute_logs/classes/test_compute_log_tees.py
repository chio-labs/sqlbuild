from unittest.mock import Mock

import pytest

from sqlbuild.compute_logs import ComputeLogStream
from sqlbuild.runtime.compute_logs.classes.binary_tee import BinaryComputeLogTee
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from tests.unit.src.sqlbuild.runtime.compute_logs.classes._test_types import (
    DetachedTeeTestCase,
    PartialWriteTestCase,
    TeeStorageFailureTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    (
        TeeStorageFailureTestCase(
            description="storage failure reports the error once and keeps writing to the sink",
            writes=("first\n", "second\n"),
            expected_sink_writes=("first\n", "second\n"),
            expected_failure_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_storage_append_failure_when_writing_text_then_callback_receives_error_once(
    test_case: TeeStorageFailureTestCase,
) -> None:
    sink: Mock = Mock()
    sink.encoding = "utf-8"
    sink.errors = "strict"
    sink.buffer = Mock()
    sink.write.return_value = None
    storage_error: OSError = OSError("controlled append failure")
    storage: Mock = Mock()
    storage.append.side_effect = storage_error
    failures: list[Exception] = []
    tee: TextComputeLogTee = TextComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="text_append_failure",
        stream=ComputeLogStream.STDERR,
        failure_callback=failures.append,
    )

    for text in test_case.writes:
        _ = tee.write(text)

    assert tuple(call.args[0] for call in sink.write.call_args_list) == (
        test_case.expected_sink_writes
    )
    assert failures == [storage_error] * test_case.expected_failure_count


@pytest.mark.parametrize(
    "test_case",
    (
        DetachedTeeTestCase(
            description="detached text and buffer writes reach the sink without retention",
            text="late text\n",
            binary=b"late bytes\n",
            expected_append_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_detached_tee_when_writing_then_sink_receives_data_without_storage_append(
    test_case: DetachedTeeTestCase,
) -> None:
    sink: Mock = Mock()
    sink.encoding = "utf-8"
    sink.errors = "strict"
    sink.buffer = Mock()
    sink.write.return_value = None
    sink.buffer.write.return_value = None
    storage: Mock = Mock()
    failures: list[Exception] = []
    tee: TextComputeLogTee = TextComputeLogTee(
        sink=sink,
        storage=storage,
        invocation_id="detached",
        stream=ComputeLogStream.STDOUT,
        failure_callback=failures.append,
    )

    tee.detach()
    _ = tee.write(test_case.text)
    _ = tee.buffer.write(test_case.binary)

    sink.write.assert_called_once_with(test_case.text)
    sink.buffer.write.assert_called_once_with(test_case.binary)
    assert storage.append.call_count == test_case.expected_append_count
    assert failures == []
