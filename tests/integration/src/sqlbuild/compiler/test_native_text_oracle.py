"""Compare native text decoding and positions with Python's read_text and column arithmetic."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from sqlbuild import _native
from tests.integration.src.sqlbuild.compiler._test_types import TextOracleTestCase
from tests.integration.src.sqlbuild.compiler.helpers import (
    authored_bytes,
    invalid_authored_bytes,
    mismatches,
    python_positions,
    python_read_text,
    random_char_offsets,
    utf8_offsets,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TextOracleTestCase(
            description="CRLF, CR, tabs and non-ASCII before every offset", seed=31, case_count=400
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_files_when_decoding_natively_then_text_and_positions_match_python(
    test_case: TextOracleTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    files: list[bytes] = [authored_bytes(rng=rng) for _ in range(test_case.case_count)]
    texts: list[str] = [python_read_text(path=tmp_path / "model.sql", data=data) for data in files]
    char_offsets: list[list[int]] = [random_char_offsets(rng=rng, text=text) for text in texts]
    byte_offsets: list[list[int]] = [
        utf8_offsets(text=text, char_offsets=offsets)
        for text, offsets in zip(texts, char_offsets, strict=True)
    ]

    expected: list[object] = [
        (text, python_positions(text=text, char_offsets=offsets))
        for text, offsets in zip(texts, char_offsets, strict=True)
    ]
    actual: list[object] = [
        _native._oracle_text_positions(data, offsets)
        for data, offsets in zip(files, byte_offsets, strict=True)
    ]

    assert mismatches(inputs=list(files), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


@pytest.mark.parametrize(
    "test_case",
    [TextOracleTestCase(description="one invalid UTF-8 sequence", seed=32, case_count=100)],
    ids=lambda case: case.description,
)
def test_given_invalid_utf8_when_decoding_natively_then_failure_offset_matches_python(
    test_case: TextOracleTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    path: Path = tmp_path / "model.sql"
    files: list[bytes] = [invalid_authored_bytes(rng=rng) for _ in range(test_case.case_count)]
    python_offsets: list[object] = []
    native_offsets: list[object] = []

    for data in files:
        with pytest.raises(UnicodeDecodeError) as python_error:
            python_read_text(path=path, data=data)
        with pytest.raises(ValueError) as native_error:
            _native._oracle_text_positions(data, [])
        python_offsets.append(python_error.value.start)
        native_offsets.append(int(str(native_error.value)))

    assert mismatches(inputs=list(files), expected=python_offsets, actual=native_offsets) == list(
        test_case.expected_mismatches
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
