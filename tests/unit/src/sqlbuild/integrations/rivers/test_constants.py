from __future__ import annotations

import pytest

from sqlbuild.compiler.dag.types import NodeKind
from sqlbuild.integrations.rivers.constants import (
    RIVERS_ASSET_NODE_KIND_EXCLUSIONS,
    RIVERS_ASSET_NODE_KIND_MEMBERS,
    RIVERS_ASSET_NODE_KINDS,
    RIVERS_DIRECT_ASSET_KIND_EXCLUSIONS,
    RIVERS_DIRECT_ASSET_KIND_MEMBERS,
    RIVERS_DIRECT_ASSET_KINDS,
)
from tests.unit.src.sqlbuild.integrations.rivers._test_types import RiversConstantGuardTestCase


@pytest.mark.parametrize(
    "test_case",
    (
        RiversConstantGuardTestCase(
            description="all Rivers node-kind sets are exhaustive",
            expected_exhaustive=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_node_kind_enum_when_deriving_rivers_sets_then_every_kind_is_decided(
    test_case: RiversConstantGuardTestCase,
) -> None:
    all_members: frozenset[NodeKind] = frozenset(NodeKind)
    derivations: tuple[tuple[frozenset[str], frozenset[NodeKind], frozenset[NodeKind]], ...] = (
        (
            RIVERS_ASSET_NODE_KINDS,
            RIVERS_ASSET_NODE_KIND_MEMBERS,
            RIVERS_ASSET_NODE_KIND_EXCLUSIONS,
        ),
        (
            RIVERS_DIRECT_ASSET_KINDS,
            RIVERS_DIRECT_ASSET_KIND_MEMBERS,
            RIVERS_DIRECT_ASSET_KIND_EXCLUSIONS,
        ),
    )

    for derived_values, included, excluded in derivations:
        assert included.isdisjoint(excluded)
        assert (included | excluded == all_members) is test_case.expected_exhaustive
        assert derived_values == frozenset(member.value for member in included)
