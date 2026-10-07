import io

import pytest

from sqlbuild.cli.entry._helpers.streams import use_utf8_stream
from tests.unit.src.sqlbuild.cli.entry._helpers._test_types import OutputStreamEncodingTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        OutputStreamEncodingTestCase(
            description="a cp1252 stream writes box drawing and symbols as UTF-8",
            encoding="cp1252",
            errors="strict",
            text="\u2713 Project compiled \u2500\u2500 orders \u2192 customers\n",
            expected_changed=True,
            expected_bytes="\u2713 Project compiled \u2500\u2500 orders \u2192 customers\n".encode(),
        ),
        OutputStreamEncodingTestCase(
            description="a lone surrogate is escaped instead of crashing",
            encoding="cp1252",
            errors="strict",
            text="orders\ud800.sql\n",
            expected_changed=True,
            expected_bytes=b"orders\\ud800.sql\n",
        ),
        OutputStreamEncodingTestCase(
            description="a UTF-8 stream under another spelling is left alone",
            encoding="UTF8",
            errors="backslashreplace",
            text="\u2713 orders\n",
            expected_changed=False,
            expected_bytes="\u2713 orders\n".encode(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stream_encoding_when_preparing_cli_output_then_any_text_is_written(
    test_case: OutputStreamEncodingTestCase,
) -> None:
    buffer: io.BytesIO = io.BytesIO()
    stream: io.TextIOWrapper = io.TextIOWrapper(
        buffer, encoding=test_case.encoding, errors=test_case.errors
    )

    changed: bool = use_utf8_stream(stream)
    _ = stream.write(test_case.text)
    stream.flush()

    assert (changed, buffer.getvalue()) == (test_case.expected_changed, test_case.expected_bytes)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
