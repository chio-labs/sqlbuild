"""Unit coverage for reusing migration fingerprints within one plan."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

import sqlbuild.compiler.planner.classes.migration_fingerprint_cache as fingerprint_cache
from sqlbuild.compiler.planner._helpers.migrations.fingerprint import build_migration_fingerprint
from sqlbuild.compiler.planner.classes.migration_fingerprint_cache import (
    MigrationFingerprintCache,
)
from tests.unit.src.sqlbuild.compiler.planner.classes._test_types import (
    MigrationFingerprintCacheTestCase,
    PersistedMigrationFingerprintTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.classes.helpers import (
    CURSOR_METADATA,
    ORDERS_SQL,
    PLAIN_METADATA,
    corrupt_database,
    count_fingerprint_computations,
    keep_cache,
    tamper_entries,
    upgrade_sqlbuild,
)

_ORDERS_SQL: str = 'SELECT o.order_id, o.amount_cents FROM __ref("stg_orders") AS o'
_CURSOR_METADATA: str = json.dumps(
    {
        "model_name": "daily_orders",
        "config": {
            "materialized": "incremental",
            "cursor_inputs": {"order_events": "event_date"},
        },
    }
)
_PLAIN_METADATA: str = json.dumps(
    {"model_name": "daily_orders", "config": {"materialized": "table"}}
)
_METADATA: dict[str, str] = {"plain": _PLAIN_METADATA, "cursor": _CURSOR_METADATA}


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationFingerprintCacheTestCase(
            description="renames of models the query never reads reuse the fingerprint",
            requests=(
                ("plain", {}, "duckdb"),
                ("plain", {"customers": "old_customers"}, "duckdb"),
                ("plain", {}, "duckdb"),
            ),
            expected_computations=1,
        ),
        MigrationFingerprintCacheTestCase(
            description="a rename of a referenced model is a distinct fingerprint",
            requests=(
                ("plain", {}, "duckdb"),
                ("plain", {"stg_orders": "old_orders"}, "duckdb"),
                ("plain", {"stg_orders": "old_orders", "customers": "x"}, "duckdb"),
            ),
            expected_computations=2,
        ),
        MigrationFingerprintCacheTestCase(
            description="a rename of a cursor input is a distinct fingerprint",
            requests=(
                ("cursor", {}, "duckdb"),
                ("cursor", {"order_events": "old_events"}, "duckdb"),
            ),
            expected_computations=2,
        ),
        MigrationFingerprintCacheTestCase(
            description="dialects and metadata never share fingerprints",
            requests=(
                ("plain", {}, "duckdb"),
                ("plain", {}, "snowflake"),
                ("cursor", {}, "duckdb"),
            ),
            expected_computations=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_requests_when_cached_then_matches_direct_build_with_minimal_work(
    test_case: MigrationFingerprintCacheTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    computations: list[int] = []

    def counting(
        *,
        query_sql: str,
        metadata_json: str,
        ref_identities: Mapping[str, str],
        dialect: str | None,
    ) -> str | None:
        computations.append(1)
        return build_migration_fingerprint(
            query_sql=query_sql,
            metadata_json=metadata_json,
            ref_identities=ref_identities,
            dialect=dialect,
        )

    monkeypatch.setattr(fingerprint_cache, "build_migration_fingerprint", counting)
    cache: MigrationFingerprintCache = MigrationFingerprintCache()

    results: list[str | None] = [
        cache.fingerprint(
            query_sql=_ORDERS_SQL,
            metadata_json=_METADATA[metadata],
            ref_identities=identities,
            dialect=dialect,
        )
        for metadata, identities, dialect in test_case.requests
    ]

    assert results == [
        build_migration_fingerprint(
            query_sql=_ORDERS_SQL,
            metadata_json=_METADATA[metadata],
            ref_identities=identities,
            dialect=dialect,
        )
        for metadata, identities, dialect in test_case.requests
    ]
    assert all(result is not None for result in results)
    assert len(computations) == test_case.expected_computations


@pytest.mark.parametrize(
    "test_case",
    [
        PersistedMigrationFingerprintTestCase(
            description="a warm cache computes nothing",
            between_runs=keep_cache,
            expected_second_run_computations=0,
        ),
        PersistedMigrationFingerprintTestCase(
            description="a corrupt database is recomputed",
            between_runs=corrupt_database,
            expected_second_run_computations=2,
        ),
        PersistedMigrationFingerprintTestCase(
            description="tampered entries are recomputed",
            between_runs=tamper_entries,
            expected_second_run_computations=2,
        ),
        PersistedMigrationFingerprintTestCase(
            description="a new sqlbuild version is recomputed",
            between_runs=upgrade_sqlbuild,
            expected_second_run_computations=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_persisted_fingerprints_when_planning_again_then_reuses_only_valid_entries(
    test_case: PersistedMigrationFingerprintTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: tuple[str, ...] = (PLAIN_METADATA, CURSOR_METADATA)
    first: MigrationFingerprintCache = MigrationFingerprintCache(root=tmp_path)
    expected: list[str | None] = [
        first.fingerprint(
            query_sql=ORDERS_SQL, metadata_json=metadata, ref_identities={}, dialect="duckdb"
        )
        for metadata in requests
    ]
    first.persist()
    test_case.between_runs(tmp_path, monkeypatch)
    computations: list[int] = count_fingerprint_computations(monkeypatch)
    second: MigrationFingerprintCache = MigrationFingerprintCache(root=tmp_path)

    results: list[str | None] = [
        second.fingerprint(
            query_sql=ORDERS_SQL, metadata_json=metadata, ref_identities={}, dialect="duckdb"
        )
        for metadata in requests
    ]
    second.persist()

    assert results == expected
    assert all(result is not None for result in results)
    assert len(computations) == test_case.expected_second_run_computations


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
