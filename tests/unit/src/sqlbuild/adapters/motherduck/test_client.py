from __future__ import annotations

import pytest

from sqlbuild.adapters.motherduck.client import MotherDuckAdapter
from tests.unit.src.sqlbuild.adapters.motherduck._test_types import (
    MotherDuckAdapterDefaultsTestCase,
    MotherDuckConnectionDatabaseTestCase,
    MotherDuckPruneSqlTestCase,
)
from tests.unit.src.sqlbuild.adapters.motherduck.helpers import (
    FakeDuckDbModule,
    install_fake_duckdb_module,
)

CONNECTION_DATABASE_TEST_CASES: list[MotherDuckConnectionDatabaseTestCase] = [
    MotherDuckConnectionDatabaseTestCase(
        description="defaults to the MotherDuck account connection",
        config={},
        expected_database="md:",
    ),
    MotherDuckConnectionDatabaseTestCase(
        description="prefixes bare database names with md scheme",
        config={"database": "analytics"},
        expected_database="md:analytics",
    ),
    MotherDuckConnectionDatabaseTestCase(
        description="preserves explicit md connection strings",
        config={"database": "md:analytics"},
        expected_database="md:analytics",
    ),
    MotherDuckConnectionDatabaseTestCase(
        description="adds token as MotherDuck connection parameter",
        config={"database": "analytics", "token": "token with space"},
        expected_database="md:analytics?motherduck_token=token+with+space",
    ),
    MotherDuckConnectionDatabaseTestCase(
        description="appends token to existing connection parameters",
        config={"database": "md:analytics?custom=1", "token": "secret"},
        expected_database="md:analytics?custom=1&motherduck_token=secret",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CONNECTION_DATABASE_TEST_CASES,
    ids=[case.description for case in CONNECTION_DATABASE_TEST_CASES],
)
def test_given_connection_config_when_connecting_then_uses_motherduck_database(
    test_case: MotherDuckConnectionDatabaseTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: MotherDuckAdapter = MotherDuckAdapter()
    fake_duckdb: FakeDuckDbModule = install_fake_duckdb_module(monkeypatch)

    adapter.connect(test_case.config)

    assert fake_duckdb.connected_databases == [test_case.expected_database]


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckAdapterDefaultsTestCase(
            description="returns MotherDuck adapter defaults",
            expected_default_schema="main",
            expected_sql_analysis_dialect="duckdb",
        )
    ],
    ids=["returns MotherDuck adapter defaults"],
)
def test_given_motherduck_adapter_when_checking_defaults_then_returns_duckdb_defaults(
    test_case: MotherDuckAdapterDefaultsTestCase,
) -> None:
    adapter: MotherDuckAdapter = MotherDuckAdapter()

    assert adapter.default_schema() == test_case.expected_default_schema
    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckPruneSqlTestCase(
            description="inherits DuckDB fingerprint pruning SQL",
            database=None,
            schema="analytics",
            retain_versions=5,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_fingerprints WHERE rowid IN",
                "PARTITION BY node_name",
                "ORDER BY ts DESC, run_id DESC",
                "__sqlbuild_history_rank > 5",
            ),
        )
    ],
    ids=["inherits DuckDB fingerprint pruning SQL"],
)
def test_given_fingerprint_table_when_rendering_prune_then_motherduck_inherits_duckdb_pattern(
    test_case: MotherDuckPruneSqlTestCase,
) -> None:
    adapter: MotherDuckAdapter = MotherDuckAdapter()

    sql: str = adapter.render_prune_fingerprint_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckPruneSqlTestCase(
            description="inherits DuckDB source freshness pruning SQL",
            database=None,
            schema="analytics",
            retain_versions=3,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_source_freshness WHERE rowid IN",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "__sqlbuild_history_rank > 3",
            ),
        )
    ],
    ids=["inherits DuckDB source freshness pruning SQL"],
)
def test_given_source_freshness_table_when_rendering_prune_then_motherduck_inherits_duckdb_pattern(
    test_case: MotherDuckPruneSqlTestCase,
) -> None:
    adapter: MotherDuckAdapter = MotherDuckAdapter()

    sql: str = adapter.render_prune_source_freshness_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql
