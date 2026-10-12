"""Compare native ports of Python string helpers with the Python standard library."""

from __future__ import annotations

import difflib
import random

import pytest

from sqlbuild import _native
from sqlbuild.compiler.discovery.constants import SQL_MODEL_HEADER_KEYS
from tests.integration.src.sqlbuild.compiler._test_types import CloseMatchesOracleTestCase
from tests.integration.src.sqlbuild.compiler.helpers import mismatches, mutated_word


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
