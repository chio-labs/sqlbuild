"""Tests for pure normalized path visibility."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes.main._normalize_scope_path import normalize_scope_path
from sqlbuild.compiler.scopes.main._path_is_equal_or_descendant import (
    path_is_equal_or_descendant,
)
from sqlbuild.compiler.scopes.main._scope_is_path_visible import scope_is_path_visible
from sqlbuild.compiler.scopes.types import ScopeKind
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
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
    assert normalize_scope_path(path=test_case.path) == test_case.expected_path


@pytest.mark.parametrize(
    "test_case",
    [
        PathVisibilityCase("global", ScopeKind.GLOBAL, "constants", "tests/orders.sql", True),
        PathVisibilityCase(
            "inherited_owner", ScopeKind.INHERITED, "models/staging", "models/staging/a.sql", True
        ),
        PathVisibilityCase(
            "inherited_descendant",
            ScopeKind.INHERITED,
            "models/staging",
            "models/staging/orders/a.sql",
            True,
        ),
        PathVisibilityCase(
            "local_owner", ScopeKind.LOCAL, "models/staging", "models/staging/a.sql", True
        ),
        PathVisibilityCase(
            "local_descendant",
            ScopeKind.LOCAL,
            "models/staging",
            "models/staging/orders/a.sql",
            False,
        ),
        PathVisibilityCase(
            "textual_prefix", ScopeKind.INHERITED, "models/order", "models/orders/a.sql", False
        ),
        PathVisibilityCase(
            "descendant_hidden",
            ScopeKind.INHERITED,
            "models/staging/orders",
            "models/staging/a.sql",
            False,
        ),
        PathVisibilityCase(
            "private", ScopeKind.PRIVATE, "models/staging", "models/staging/a.sql", False
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scope_and_resource_path_when_resolving_then_enforces_component_visibility(
    test_case: PathVisibilityCase,
) -> None:
    assert (
        scope_is_path_visible(
            scope=test_case.scope,
            owning_path=test_case.owner,
            resource_path=test_case.resource,
        )
        is test_case.expected_visible
    )


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
        path_is_equal_or_descendant(path=test_case.resource, ancestor=test_case.owner)
        is test_case.expected_visible
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
