"""Integration coverage for fresh migration stage and displaced-destination names."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.migrations._helpers.naming import resolve_artifact_names
from sqlbuild.executor.migrations.models import MigrationArtifactNames
from tests.integration.src.sqlbuild.executor.migrations._helpers._test_types import (
    ArtifactNamingTestCase,
)
from tests.integration.src.sqlbuild.executor.migrations._helpers.helpers import (
    orders_migration_entry,
)

_NOW: datetime = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        ArtifactNamingTestCase(
            description="unused names take the current second and see a missing destination",
            existing_relations=(),
            now=_NOW,
            expected_stage_name="_sqb_archive__20260102t030405z__migration_stage__orders_v2",
            expected_displaced_name=(
                "_sqb_archive__20260102t030405z__migration_previous__orders_v2"
            ),
            expected_destination_exists=False,
        ),
        ArtifactNamingTestCase(
            description="an abandoned stage from the same second steps back one second",
            existing_relations=(
                "orders_v2",
                "_sqb_archive__20260102t030405z__migration_stage__orders_v2",
            ),
            now=_NOW,
            expected_stage_name="_sqb_archive__20260102t030404z__migration_stage__orders_v2",
            expected_displaced_name=(
                "_sqb_archive__20260102t030404z__migration_previous__orders_v2"
            ),
            expected_destination_exists=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_relations_when_resolving_names_then_never_reuses_an_existing_stage(
    test_case: ArtifactNamingTestCase,
) -> None:
    """Every attempt stages under a name that did not exist when the attempt began."""

    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    name: str
    for name in test_case.existing_relations:
        _ = adapter.execute(
            connection=connection, sql=f"CREATE TABLE main.{name} AS SELECT 1 AS id"
        )

    names: MigrationArtifactNames = resolve_artifact_names(
        adapter=adapter, connection=connection, entry=orders_migration_entry(), now=test_case.now
    )

    assert names.stage_name == test_case.expected_stage_name
    assert names.displaced_name == test_case.expected_displaced_name
    assert names.destination_exists is test_case.expected_destination_exists
    assert names.stage_qualified == f"main.{test_case.expected_stage_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
