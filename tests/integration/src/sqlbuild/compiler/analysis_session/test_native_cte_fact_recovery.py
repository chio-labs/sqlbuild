"""Native CTE fact recovery matches the facts recorded from Python's recovery, query by query."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from tests.integration.src.sqlbuild.compiler.analysis_session._test_helpers import (
    CteFactParity,
    compare_cte_facts,
    generated_cte_fact_query,
)
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    CteFactRecoveryParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.golden_views import (
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CteFactRecoveryParityTestCase(
            description="casts, CASE, COALESCE, IF/IFF, adapter rules, set operations, stars, joins, filters",
            seed=20261009,
            count=5000,
            expected_minimum_compared=4319,
            expected_minimum_recovered={
                "types": 1243,
                "nullability": 417,
                "direct": 859,
                "non_null": 38,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_cte_queries_when_recovering_facts_natively_then_matches_recorded_python(
    test_case: CteFactRecoveryParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    parity: CteFactParity = CteFactParity(queries=[], native=[], counts=Counter())
    for _ in range(test_case.count):
        compare_cte_facts(query=generated_cte_fact_query(rng=rng), parity=parity)

    assert (
        golden_differences(
            read_golden(golden_name("cte_facts", test_case.description)),
            [golden_entry("cte_facts", view) for view in parity.native],
        )
        == []
    )
    assert parity.counts["compared"] >= test_case.expected_minimum_compared
    assert {
        kind: parity.counts[f"recovered_{kind}"] >= minimum
        for kind, minimum in test_case.expected_minimum_recovered.items()
    } == dict.fromkeys(test_case.expected_minimum_recovered, True)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
