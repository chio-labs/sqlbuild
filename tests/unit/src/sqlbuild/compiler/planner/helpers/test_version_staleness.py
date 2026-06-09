from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.version_staleness import (
    build_stale_model_names_from_version_identities,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import VersionStalenessTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        VersionStalenessTestCase(
            description="preserves model order while marking missing mismatched and forced stale",
            model_names=("current", "missing", "mismatched", "forced"),
            expected_version_hashes={
                "current": "hash_a",
                "missing": "hash_b",
                "mismatched": "hash_c",
                "forced": "hash_d",
            },
            built_version_hashes={
                "current": "hash_a",
                "mismatched": "old_hash",
                "forced": "hash_d",
            },
            forced_stale_model_names=("forced",),
            expected_stale_model_names=("missing", "mismatched", "forced"),
        )
    ],
    ids=["preserves model order while marking missing mismatched and forced stale"],
)
def test_given_version_identity_maps_when_collecting_stale_models_then_returns_expected_names(
    test_case: VersionStalenessTestCase,
) -> None:
    result: tuple[str, ...] = build_stale_model_names_from_version_identities(
        model_names=test_case.model_names,
        expected_version_hashes=test_case.expected_version_hashes,
        built_version_hashes=test_case.built_version_hashes,
        forced_stale_model_names=test_case.forced_stale_model_names,
    )

    assert result == test_case.expected_stale_model_names
