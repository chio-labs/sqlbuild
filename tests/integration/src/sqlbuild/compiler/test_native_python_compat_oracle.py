"""Compare native ports of Python string helpers with the Python standard library."""

from __future__ import annotations

import difflib
import inspect
import random
import sys
import unicodedata

import pytest

from sqlbuild import _native
from sqlbuild.compiler.discovery.constants import SQL_MODEL_HEADER_KEYS
from tests.integration.src.sqlbuild.compiler._test_types import (
    CharacterClassOracleTestCase,
    CleandocOracleTestCase,
    CloseMatchesOracleTestCase,
)
from tests.integration.src.sqlbuild.compiler.helpers import (
    cleandoc_text,
    mismatches,
    mutated_word,
)

RUNTIME: tuple[tuple[int, int], str] = (
    (sys.version_info[0], sys.version_info[1]),
    unicodedata.unidata_version,
)
NATIVE_TEXT_SUPPORTED: bool = _native.native_text_supported(*RUNTIME)
UNSUPPORTED_REASON: str = "native discovery defers to Python on this Python or Unicode version"


@pytest.mark.skipif(not NATIVE_TEXT_SUPPORTED, reason=UNSUPPORTED_REASON)
@pytest.mark.parametrize(
    "test_case",
    [CharacterClassOracleTestCase(description="every code point", first=0, last=sys.maxunicode)],
    ids=lambda case: case.description,
)
def test_given_code_points_when_classifying_natively_then_isalnum_matches_python(
    test_case: CharacterClassOracleTestCase,
) -> None:
    code_points: list[int] = list(range(test_case.first, test_case.last + 1))

    expected: list[object] = [chr(code_point).isalnum() for code_point in code_points]
    actual: list[object] = list(_native._oracle_python_alnum(*RUNTIME, code_points) or ())

    assert mismatches(inputs=list(code_points), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CloseMatchesOracleTestCase(
            description="mutated header keys, best match only",
            seed=51,
            case_count=600,
            count=1,
            cutoff=0.6,
        ),
        CloseMatchesOracleTestCase(
            description="mutated header keys, ranked with a low cutoff",
            seed=52,
            case_count=300,
            count=4,
            cutoff=0.2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_words_when_finding_close_matches_natively_then_difflib_agrees(
    test_case: CloseMatchesOracleTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    candidates: list[str] = sorted(SQL_MODEL_HEADER_KEYS)
    words: list[str] = [
        mutated_word(rng=rng, candidates=candidates) for _ in range(test_case.case_count)
    ]

    expected: list[object] = [
        difflib.get_close_matches(word, candidates, n=test_case.count, cutoff=test_case.cutoff)
        for word in words
    ]
    actual: list[object] = [
        _native._oracle_close_matches(word, candidates, test_case.count, test_case.cutoff)
        for word in words
    ]

    assert mismatches(inputs=list(words), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


@pytest.mark.skipif(not NATIVE_TEXT_SUPPORTED, reason=UNSUPPORTED_REASON)
@pytest.mark.parametrize(
    "test_case",
    [
        CleandocOracleTestCase(
            description="indented bodies with tabs and blank lines", seed=53, case_count=3000
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bodies_when_cleaning_natively_then_inspect_cleandoc_agrees(
    test_case: CleandocOracleTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    texts: list[str] = [cleandoc_text(rng=rng) for _ in range(test_case.case_count)]

    expected: list[object] = [inspect.cleandoc(text) for text in texts]
    actual: list[object] = list(_native._oracle_cleandoc(*RUNTIME, texts) or ())

    assert mismatches(inputs=list(texts), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )
