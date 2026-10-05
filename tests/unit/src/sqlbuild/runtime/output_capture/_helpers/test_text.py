"""Tests for deterministic output capture text chunking."""

import time

import pytest

from sqlbuild.runtime.output_capture._helpers.text import chunk_text
from tests.unit.src.sqlbuild.runtime.output_capture._helpers._test_types import (
    ChunkTextErrorTestCase,
    ChunkTextFunction,
    ChunkTextOracleTestCase,
    ChunkTextPerformanceTestCase,
    ChunkTextTestCase,
)
from tests.unit.src.sqlbuild.runtime.output_capture._helpers.helpers import (
    random_mixed_width_texts,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ChunkTextTestCase("two_byte_straddles_limit", "aé", 2, ("a", "é")),
        ChunkTextTestCase("three_byte_straddles_limit", "ab订c", 4, ("ab", "订c")),
        ChunkTextTestCase("four_byte_straddles_limit", "abc📦", 4, ("abc", "📦")),
        ChunkTextTestCase("four_byte_exact_limit", "📦📦", 4, ("📦", "📦")),
        ChunkTextTestCase("combining_mark_split_from_base", "ée\u0301", 4, ("ée", "\u0301")),
        ChunkTextTestCase("character_wider_than_limit", "a📦b", 2, ("a", "📦", "b")),
        ChunkTextTestCase("each_character_when_limit_zero", "a订", 0, ("a", "订")),
        ChunkTextTestCase("empty_text_negative_limit", "", -1, ("",)),
        ChunkTextTestCase("escaped_surrogate_counts_one_byte", "é\udc80a", 3, ("é\udc80", "a")),
    ),
    ids=lambda case: case.description,
)
def test_given_multibyte_boundaries_when_chunking_then_code_points_stay_whole(
    test_case: ChunkTextTestCase,
    reference_chunk_text: ChunkTextFunction,
) -> None:
    result: tuple[str, ...] = chunk_text(text=test_case.text, max_bytes=test_case.max_bytes)

    assert result == test_case.expected_chunks
    assert result == reference_chunk_text(text=test_case.text, max_bytes=test_case.max_bytes)


@pytest.mark.parametrize(
    "test_case",
    (ChunkTextErrorTestCase("unescapable_surrogate", "é\ud800", 2, UnicodeEncodeError),),
    ids=lambda case: case.description,
)
def test_given_unescapable_surrogate_when_chunking_then_raises_like_reference(
    test_case: ChunkTextErrorTestCase,
    reference_chunk_text: ChunkTextFunction,
) -> None:
    with pytest.raises(test_case.expected_error):
        _ = reference_chunk_text(text=test_case.text, max_bytes=test_case.max_bytes)
    with pytest.raises(test_case.expected_error):
        _ = chunk_text(text=test_case.text, max_bytes=test_case.max_bytes)


@pytest.mark.parametrize(
    "test_case",
    [
        ChunkTextOracleTestCase(
            f"limit_{max_bytes}",
            seed=max_bytes,
            max_bytes=max_bytes,
            count=400,
            expected_mismatch_count=0,
        )
        for max_bytes in (1, 2, 3, 4, 5, 6, 7, 8, 13, 64, 257)
    ],
    ids=lambda case: case.description,
)
def test_given_random_mixed_width_text_when_chunking_then_matches_reference(
    test_case: ChunkTextOracleTestCase,
    reference_chunk_text: ChunkTextFunction,
) -> None:
    texts: tuple[str, ...] = random_mixed_width_texts(
        seed=test_case.seed, max_bytes=test_case.max_bytes, count=test_case.count
    )

    actual: tuple[tuple[str, ...], ...] = tuple(
        chunk_text(text=text, max_bytes=test_case.max_bytes) for text in texts
    )

    expected: tuple[tuple[str, ...], ...] = tuple(
        reference_chunk_text(text=text, max_bytes=test_case.max_bytes) for text in texts
    )
    mismatch_count: int = sum(
        result != reference for result, reference in zip(actual, expected, strict=True)
    )
    assert mismatch_count == test_case.expected_mismatch_count
    assert tuple("".join(chunks) for chunks in actual) == texts


@pytest.mark.parametrize(
    "test_case",
    (
        ChunkTextPerformanceTestCase(
            "non_ascii_ten_megabytes",
            unit="order ünïcode 订单 📦 e\u0301 ",
            payload_bytes=10_000_000,
            max_bytes=64 * 1024,
            expected_max_seconds=0.1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_large_non_ascii_payload_when_chunking_then_completes_within_budget(
    test_case: ChunkTextPerformanceTestCase,
) -> None:
    unit_bytes: int = len(test_case.unit.encode("utf-8"))
    text: str = test_case.unit * (test_case.payload_bytes // unit_bytes + 1)
    timings: list[float] = []
    result: tuple[str, ...] = ()

    for _ in range(3):
        started: float = time.perf_counter()
        result = chunk_text(text=text, max_bytes=test_case.max_bytes)
        timings.append(time.perf_counter() - started)

    assert "".join(result) == text
    assert all(len(chunk.encode("utf-8")) <= test_case.max_bytes for chunk in result)
    assert min(timings) < test_case.expected_max_seconds


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
