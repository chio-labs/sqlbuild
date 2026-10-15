from __future__ import annotations

import pytest

from sqlbuild._native import (
    DirectModelVersionIdentities,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity._test_types import (
    DeepChainIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity.helpers import (
    build_chain_graph_identities,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeepChainIdentityTestCase(
            description="one hundred thousand chained models",
            depth=100_000,
            expected_hash_count=100_000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deep_model_chain_when_building_identities_then_resolves_every_model(
    test_case: DeepChainIdentityTestCase,
) -> None:
    identities: DirectModelVersionIdentities = build_chain_graph_identities(depth=test_case.depth)

    assert len(identities.model_version_hashes) == test_case.expected_hash_count
