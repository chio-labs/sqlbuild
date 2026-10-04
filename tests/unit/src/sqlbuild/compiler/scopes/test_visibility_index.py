"""Equivalence of indexed scope visibility with the exhaustive per-declaration classification."""

from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.compiler.scopes._test_helpers import (
    declaration_visibility_mismatches,
    random_scope_lookup,
    visibility_mismatches,
)
from tests.unit.src.sqlbuild.compiler.scopes._test_types import RandomScopeCase


@pytest.mark.parametrize(
    "test_case",
    [
        RandomScopeCase("sparse", seed=1, resource_count=12, declaration_count=20, grant_count=0),
        RandomScopeCase("mixed", seed=2, resource_count=30, declaration_count=60, grant_count=6),
        RandomScopeCase("dense", seed=3, resource_count=50, declaration_count=120, grant_count=15),
        RandomScopeCase(
            "no_declarations", seed=4, resource_count=8, declaration_count=0, grant_count=0
        ),
        RandomScopeCase(
            "grant_heavy", seed=5, resource_count=40, declaration_count=80, grant_count=40
        ),
        RandomScopeCase("wide", seed=6, resource_count=25, declaration_count=200, grant_count=3),
    ],
    ids=lambda case: case.description,
)
def test_given_randomized_scopes_when_resolving_visibility_then_matches_exhaustive_classification(
    test_case: RandomScopeCase,
) -> None:
    mismatches: tuple[str, ...] = visibility_mismatches(
        lookup=random_scope_lookup(
            seed=test_case.seed,
            resource_count=test_case.resource_count,
            declaration_count=test_case.declaration_count,
            grant_count=test_case.grant_count,
        )
    )

    assert mismatches == test_case.expected_mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        RandomScopeCase("sparse", seed=1, resource_count=12, declaration_count=20, grant_count=0),
        RandomScopeCase("mixed", seed=2, resource_count=30, declaration_count=60, grant_count=6),
        RandomScopeCase(
            "grant_heavy", seed=5, resource_count=40, declaration_count=80, grant_count=40
        ),
        RandomScopeCase("wide", seed=6, resource_count=25, declaration_count=200, grant_count=3),
    ],
    ids=lambda case: case.description,
)
def test_given_randomized_scopes_when_resolving_declarations_then_matches_exhaustive_identities(
    test_case: RandomScopeCase,
) -> None:
    mismatches: tuple[str, ...] = declaration_visibility_mismatches(
        lookup=random_scope_lookup(
            seed=test_case.seed,
            resource_count=test_case.resource_count,
            declaration_count=test_case.declaration_count,
            grant_count=test_case.grant_count,
        )
    )

    assert mismatches == test_case.expected_mismatches


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
