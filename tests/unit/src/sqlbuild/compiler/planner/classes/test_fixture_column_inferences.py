"""Unit coverage for reusing fixture column inference within one planning run."""

from __future__ import annotations

import pytest

from sqlbuild._native import (
    FixtureColumnInference,
    FixtureColumnInferences,
    fixture_inference_count,
    infer_fixture_column_facts,
)
from tests.unit.src.sqlbuild.compiler.planner.classes._test_types import (
    FixtureColumnInferencesTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.classes.helpers import (
    FIXTURE_PROFILES,
    FIXTURE_QUERIES,
    reset_fixture_inference_count,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FixtureColumnInferencesTestCase(
            description="identical fixture bodies under equal profiles infer once",
            requests=(("orders", "duckdb"), ("orders", "duckdb_again"), ("orders", "duckdb")),
            expected_inferences=1,
        ),
        FixtureColumnInferencesTestCase(
            description="different bodies and dialects infer separately",
            requests=(("orders", "duckdb"), ("customers", "duckdb"), ("orders", "snowflake")),
            expected_inferences=3,
        ),
        FixtureColumnInferencesTestCase(
            description="profiles with a binding catalog are never reused",
            requests=(("orders", "catalog"), ("orders", "catalog")),
            expected_inferences=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fixture_queries_when_inferring_then_matches_direct_inference_with_minimal_work(
    test_case: FixtureColumnInferencesTestCase,
) -> None:
    reset_fixture_inference_count()
    memo: FixtureColumnInferences = FixtureColumnInferences()

    results: list[FixtureColumnInference | None] = [
        memo.infer(query_sql=FIXTURE_QUERIES[query], inference_profile=FIXTURE_PROFILES[profile])
        for query, profile in test_case.requests
    ]
    inferences: int = fixture_inference_count()

    assert results == [
        infer_fixture_column_facts(
            query_sql=FIXTURE_QUERIES[query], inference_profile=FIXTURE_PROFILES[profile]
        )
        for query, profile in test_case.requests
    ]
    assert all(result is not None for result in results)
    assert inferences == test_case.expected_inferences


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
