from __future__ import annotations

import pytest

from scripts.dupscore._helpers.clones.clustering import cluster_clone_pairs
from scripts.dupscore.constants import CATEGORY_EXACT, CATEGORY_NEAR_MISS, CATEGORY_RENAMED
from scripts.dupscore.models import CloneCluster
from tests.unit.scripts.dupscore._helpers.clones.clustering._test_types import (
    ClusterEstimateTestCase,
    ClusterPairsTestCase,
    ForcedClusterTestCase,
)
from tests.unit.scripts.dupscore._helpers.clones.clustering.helpers import (
    build_pairs,
    build_units,
    no_change,
    summarize_clusters,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClusterPairsTestCase(
            description="transitive pairs merge and rank by duplicated tokens",
            pairs=(
                (3, 4, 1.0, CATEGORY_EXACT),
                (0, 1, 1.0, CATEGORY_RENAMED),
                (1, 2, 0.9, CATEGORY_NEAR_MISS),
            ),
            expected_clusters=(
                (CATEGORY_NEAR_MISS, ("function_0", "function_1", "function_2")),
                (CATEGORY_EXACT, ("function_3", "function_4")),
            ),
        ),
        ClusterPairsTestCase(
            description="no pairs means no clusters",
            pairs=(),
            expected_clusters=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_pairs_when_clustering_then_groups_transitively(
    test_case: ClusterPairsTestCase,
) -> None:
    clusters: list[CloneCluster] = cluster_clone_pairs(
        units=build_units(),
        pairs=build_pairs(test_case.pairs),
        change_of=no_change,
        forced=frozenset(),
    )

    assert summarize_clusters(clusters) == test_case.expected_clusters


@pytest.mark.parametrize(
    "test_case",
    [
        ClusterEstimateTestCase(
            description="chain reports member links and duplicated token estimate",
            pairs=((0, 1, 1.0, CATEGORY_RENAMED), (1, 2, 0.9, CATEGORY_NEAR_MISS)),
            expected_links=((0, 1), (1, 2)),
            expected_similarity_range=(0.9, 1.0),
            expected_duplicated_tokens=181,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cluster_when_clustering_then_reports_links_and_estimates(
    test_case: ClusterEstimateTestCase,
) -> None:
    cluster: CloneCluster = cluster_clone_pairs(
        units=build_units(),
        pairs=build_pairs(test_case.pairs),
        change_of=no_change,
        forced=frozenset(),
    )[0]

    assert tuple((link.left, link.right) for link in cluster.links) == test_case.expected_links
    assert (cluster.similarity_min, cluster.similarity_max) == test_case.expected_similarity_range
    assert cluster.duplicated_tokens == test_case.expected_duplicated_tokens


@pytest.mark.parametrize(
    "test_case",
    [
        ForcedClusterTestCase(
            description="forced members sort last and add no duplicated tokens",
            pairs=((0, 3, 1.0, CATEGORY_EXACT), (1, 3, 1.0, CATEGORY_EXACT)),
            forced=frozenset({0, 1}),
            expected_members=(
                ("function_3", False),
                ("function_0", True),
                ("function_1", True),
            ),
            expected_links=((0, 1), (0, 2)),
            expected_duplicated_tokens=40,
        ),
        ForcedClusterTestCase(
            description="without forced members one copy is kept out of the estimate",
            pairs=((0, 3, 1.0, CATEGORY_EXACT), (1, 3, 1.0, CATEGORY_EXACT)),
            forced=frozenset(),
            expected_members=(
                ("function_0", False),
                ("function_1", False),
                ("function_3", False),
            ),
            expected_links=((0, 2), (1, 2)),
            expected_duplicated_tokens=140,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_forced_members_when_clustering_then_orders_marks_and_estimates(
    test_case: ForcedClusterTestCase,
) -> None:
    cluster: CloneCluster = cluster_clone_pairs(
        units=build_units(),
        pairs=build_pairs(test_case.pairs),
        change_of=no_change,
        forced=test_case.forced,
    )[0]

    assert (
        tuple((member.name, member.forced_override) for member in cluster.members)
        == test_case.expected_members
    )
    assert tuple((link.left, link.right) for link in cluster.links) == test_case.expected_links
    assert cluster.duplicated_tokens == test_case.expected_duplicated_tokens
