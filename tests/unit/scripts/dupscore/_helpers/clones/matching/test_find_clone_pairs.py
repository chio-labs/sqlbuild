from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.fingerprints import fingerprint_tokens
from scripts.dupscore._helpers.clones.matching import find_clone_pairs
from scripts.dupscore.constants import CATEGORY_NEAR_MISS
from scripts.dupscore.models import ClonePair, CloneUnit
from tests.unit.scripts.dupscore._helpers.clones.matching._test_types import (
    NearMissFloorTestCase,
)
from tests.unit.scripts.dupscore._helpers.clones.matching.helpers import diverging_unit


@pytest.mark.parametrize(
    "test_case",
    [
        NearMissFloorTestCase(
            description="short pair below the small-unit similarity floor is dropped",
            shared_tokens=60,
            differing_tokens=10,
            min_similarity=0.8,
            expected_categories=[],
        ),
        NearMissFloorTestCase(
            description="short pair above the small-unit similarity floor is kept",
            shared_tokens=66,
            differing_tokens=4,
            min_similarity=0.8,
            expected_categories=[CATEGORY_NEAR_MISS],
        ),
        NearMissFloorTestCase(
            description="larger pair with the same ratio uses the configured threshold",
            shared_tokens=86,
            differing_tokens=14,
            min_similarity=0.8,
            expected_categories=[CATEGORY_NEAR_MISS],
        ),
        NearMissFloorTestCase(
            description="a stricter configured threshold still applies to short pairs",
            shared_tokens=66,
            differing_tokens=4,
            min_similarity=0.95,
            expected_categories=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_near_miss_pair_when_matching_then_applies_size_dependent_floor(
    test_case: NearMissFloorTestCase,
) -> None:
    units: list[CloneUnit] = [
        diverging_unit(
            name=side,
            shared_tokens=test_case.shared_tokens,
            differing_tokens=test_case.differing_tokens,
        )
        for side in ("left", "right")
    ]

    pairs: list[ClonePair] = find_clone_pairs(
        units=units,
        fingerprints=[fingerprint_tokens(unit.normalized) for unit in units],
        min_similarity=test_case.min_similarity,
    )

    assert [pair.category for pair in pairs] == test_case.expected_categories
