"""Tests for recognizing queries changed only by references rewritten for renamed models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.changes.reference_renames import origin_reference_names
from sqlbuild.compiler.planner.models import ReferenceRename
from tests.unit.src.sqlbuild.compiler.planner._helpers.changes._test_types import (
    OriginReferenceNamesTestCase,
)

_BUILT_AT: datetime = datetime(2026, 9, 1, tzinfo=UTC)
_RENAMED_AFTER_BUILD: datetime = datetime(2026, 9, 2, tzinfo=UTC)
_RENAMED_BEFORE_BUILD: datetime = datetime(2026, 8, 31, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        OriginReferenceNamesTestCase(
            description="planned rename maps the reference back outside comments",
            query_sql='-- __ref("orders")\nSELECT * FROM __ref("orders_v2")',
            recorded_query_sql='-- __ref("orders")\nSELECT * FROM __ref("orders")',
            renames=(ReferenceRename(new_name="orders_v2", origin_name="orders"),),
            expected_mapping={"orders_v2": "orders"},
        ),
        OriginReferenceNamesTestCase(
            description="names inside string literals are never substituted",
            query_sql='SELECT \'__ref("orders_v2")\' AS note, * FROM __ref("orders_v2")',
            recorded_query_sql='SELECT \'__ref("orders")\' AS note, * FROM __ref("orders")',
            renames=(ReferenceRename(new_name="orders_v2", origin_name="orders"),),
            expected_mapping=None,
        ),
        OriginReferenceNamesTestCase(
            description="recorded rename after the downstream build maps back",
            query_sql='SELECT * FROM __ref("orders_v2")',
            recorded_query_sql='SELECT * FROM __ref("orders")',
            renames=(
                ReferenceRename(
                    new_name="orders_v2", origin_name="orders", recorded_at=_RENAMED_AFTER_BUILD
                ),
            ),
            expected_mapping={"orders_v2": "orders"},
        ),
        OriginReferenceNamesTestCase(
            description="recorded rename before the downstream build is ignored",
            query_sql='SELECT * FROM __ref("orders_v2")',
            recorded_query_sql='SELECT * FROM __ref("orders")',
            renames=(
                ReferenceRename(
                    new_name="orders_v2", origin_name="orders", recorded_at=_RENAMED_BEFORE_BUILD
                ),
            ),
            expected_mapping=None,
        ),
        OriginReferenceNamesTestCase(
            description="chained renames map back to the oldest recorded name",
            query_sql='SELECT * FROM __ref("orders_v3")',
            recorded_query_sql='SELECT * FROM __ref("orders")',
            renames=(
                ReferenceRename(
                    new_name="orders_v2", origin_name="orders", recorded_at=_RENAMED_AFTER_BUILD
                ),
                ReferenceRename(new_name="orders_v3", origin_name="orders_v2"),
            ),
            expected_mapping={"orders_v3": "orders"},
        ),
        OriginReferenceNamesTestCase(
            description="a real edit alongside the rewritten reference is not reference-only",
            query_sql='SELECT id, 1 AS flag FROM __ref("orders_v2")',
            recorded_query_sql='SELECT id FROM __ref("orders")',
            renames=(ReferenceRename(new_name="orders_v2", origin_name="orders"),),
            expected_mapping=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_references_when_matching_recorded_query_then_returns_mapping(
    test_case: OriginReferenceNamesTestCase,
) -> None:
    recorded: Fingerprint = Fingerprint(
        node_type="model",
        node_name="order_summary",
        target_database=None,
        target_schema="main",
        target_name="order_summary",
        run_id="run",
        definition_hash=compute_query_hash(test_case.recorded_query_sql),
        schema_fingerprint="",
        definition=test_case.recorded_query_sql,
        ts=_BUILT_AT,
    )

    assert (
        origin_reference_names(
            query_sql=test_case.query_sql,
            recorded=recorded,
            renames=test_case.renames,
            dialect="duckdb",
        )
        == test_case.expected_mapping
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
