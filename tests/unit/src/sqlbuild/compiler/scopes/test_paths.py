"""Tests for pure normalized path visibility."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant, normalize_path
from sqlbuild.compiler.scopes.types import ScopeKind
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
    PathNormalizationCacheCase,
    PathNormalizationCase,
    PathVisibilityCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PathNormalizationCase(
            description="posix_redundant_components",
            path="models/./staging/orders/../stg_orders.sql",
            expected_path="models/staging/stg_orders.sql",
        ),
        PathNormalizationCase(
            description="windows_separators",
            path=r"models\staging\orders\stg_orders.sql",
            expected_path="models/staging/orders/stg_orders.sql",
        ),
        PathNormalizationCase(
            description="repeated_separators",
            path="models//staging///stg_orders.sql",
            expected_path="models/staging/stg_orders.sql",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_posix_or_windows_path_when_normalizing_then_returns_canonical_posix_path(
    test_case: PathNormalizationCase,
) -> None:
    assert normalize_path(path=test_case.path) == test_case.expected_path


@pytest.mark.parametrize(
    "test_case",
    [
        PathNormalizationCacheCase(
            description="repeated canonical path uses one normalization result",
            path="models/commerce/orders.sql",
            call_count=1_000,
            expected_hits=999,
            expected_misses=1,
            expected_max_size=65_536,
            expected_current_size=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_path_when_normalizing_then_reuses_bounded_cache(
    test_case: PathNormalizationCacheCase,
) -> None:
    normalize_path.cache_clear()

    for _ in range(test_case.call_count):
        _ = normalize_path(path=test_case.path)

    assert normalize_path.cache_info().hits == test_case.expected_hits
    assert normalize_path.cache_info().misses == test_case.expected_misses
    assert normalize_path.cache_info().maxsize == test_case.expected_max_size
    assert normalize_path.cache_info().currsize == test_case.expected_current_size
    normalize_path.cache_clear()


@pytest.mark.parametrize(
    "test_case",
    [
        PathVisibilityCase(
            "component_prefix", ScopeKind.INHERITED, "models/order", "models/orders", False
        )
    ],
    ids=lambda case: case.description,
)
def test_given_component_prefix_only_when_comparing_descendant_then_returns_false(
    test_case: PathVisibilityCase,
) -> None:
    assert (
        is_equal_or_descendant(path=test_case.resource, ancestor=test_case.owner)
        is test_case.expected_visible
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
