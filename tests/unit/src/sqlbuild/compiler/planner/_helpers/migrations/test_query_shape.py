"""Pinned query-shape and fingerprint evidence for structured expressions."""

from __future__ import annotations

import hashlib

import pytest

from sqlbuild._native import (
    QueryShape,
    build_migration_fingerprint,
    parse_query_shape,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations._test_types import (
    StoredProjectionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredProjectionTestCase(
            description="CASE tuple pairs preserve recorded proof boundaries",
            query_sql='SELECT CASE WHEN amount > 1 THEN amount ELSE 0 END AS total FROM __ref("orders")',
            expected_references=frozenset(),
            expected_expression_hash="3b459b87711a9f5500b8f13f9c7eadae4da1d8245d67cdf926f57179a0f339a1",
            expected_fingerprint="734b3eafe12854d5451634531a66bc6971a229549ceabd25e23e72637f1346f9",
        ),
        StoredProjectionTestCase(
            description="struct references retain their expression identity",
            query_sql="SELECT {'total': amount} AS details FROM __ref(\"orders\")",
            expected_references=frozenset({"amount"}),
            expected_expression_hash="a160e71b93536688672e65f73ca5ff09ac0020689aad1b4282c64b8c03a664f5",
            expected_fingerprint="ed1d753dd09893556d7fa08c91c8ce431600419dafd80939e843013ab705edb5",
        ),
        StoredProjectionTestCase(
            description="decode references retain their expression identity",
            query_sql='SELECT DECODE(amount, 1, 2, 0) AS total FROM __ref("orders")',
            expected_references=frozenset({"amount"}),
            expected_expression_hash="210d8215f7e3655cf5482d4e7c5026fad6f3c2a2b63f762c3bdcde05d7929ba7",
            expected_fingerprint="6e71b7abdf66bbb2f7c97b64deaf3d63a25d3d7c0e04b7d904e9b67a5af30619",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_structured_expression_when_proving_migration_then_preserves_recorded_identity(
    test_case: StoredProjectionTestCase,
) -> None:
    shape: QueryShape | None = parse_query_shape(query_sql=test_case.query_sql, dialect="duckdb")
    assert shape is not None
    assert shape.projections[0].references == test_case.expected_references
    assert (
        hashlib.sha256(shape.projections[0].expression.encode()).hexdigest()
        == test_case.expected_expression_hash
    )
    assert (
        build_migration_fingerprint(
            query_sql=test_case.query_sql,
            metadata_json="{}",
            ref_identities={},
            dialect="duckdb",
        )
        == test_case.expected_fingerprint
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
