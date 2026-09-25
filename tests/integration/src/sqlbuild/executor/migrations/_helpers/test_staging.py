"""Integration coverage for the clone-refusal copy fallback when creating a migration stage."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.executor.migrations._helpers.staging import create_stage
from sqlbuild.executor.migrations.models import MigrationArtifactNames
from tests.integration.src.sqlbuild.executor.migrations._helpers._test_types import (
    CloneFailureTestCase,
    CloneFallbackTestCase,
)
from tests.integration.src.sqlbuild.executor.migrations._helpers.helpers import (
    CloneRefusingDuckDbAdapter,
    artifact_names_for,
    orders_migration_entry,
)

_STAGE: str = "_sqb_archive__20260102t030405z__migration_stage__orders_v2"


@pytest.mark.parametrize(
    "test_case",
    [
        CloneFallbackTestCase(
            description="recognized clone refusal falls back to a physical copy",
            clone_statements=("SELECT error('clone refused by warehouse')",),
            refused_messages=("clone refused by warehouse",),
            expected_transfer=MigrationTransfer.COPY.value,
            expected_stage_rows=2,
        ),
        CloneFallbackTestCase(
            description="successful clone reports the planned clone transfer",
            clone_statements=("CREATE TABLE {stage} AS SELECT * FROM {origin}",),
            refused_messages=("clone refused by warehouse",),
            expected_transfer=MigrationTransfer.CLONE.value,
            expected_stage_rows=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_outcome_when_creating_stage_then_reports_actual_transfer(
    test_case: CloneFallbackTestCase,
) -> None:
    """The returned transfer is the one that actually populated the stage."""

    adapter: CloneRefusingDuckDbAdapter = CloneRefusingDuckDbAdapter(
        clone_statements=test_case.clone_statements, refused_messages=test_case.refused_messages
    )
    connection: Any = adapter.connect({"database": ":memory:"})
    _ = adapter.execute(
        connection=connection, sql="CREATE TABLE main.orders AS SELECT * FROM range(2) t(id)"
    )
    names: MigrationArtifactNames = artifact_names_for(stage_name=_STAGE)

    transfer: MigrationTransfer = create_stage(
        adapter=adapter, connection=connection, entry=orders_migration_entry(), names=names
    )

    assert transfer.value == test_case.expected_transfer
    assert adapter.execute(
        connection=connection, sql=f"SELECT COUNT(*) FROM {names.stage_qualified}"
    ).fetchall() == [(test_case.expected_stage_rows,)]


@pytest.mark.parametrize(
    "test_case",
    [
        CloneFailureTestCase(
            description="unrecognized failure is re-raised without attempting a copy",
            clone_statements=("SELECT error('connection reset by peer')",),
            refused_messages=("clone refused by warehouse",),
            expected_error_fragment="connection reset by peer",
            expected_stage_exists=False,
        ),
        CloneFailureTestCase(
            description="refusal after the stage appeared fails instead of adopting it",
            clone_statements=(
                "CREATE TABLE {stage} AS SELECT * FROM {origin}",
                "SELECT error('clone refused by warehouse')",
            ),
            refused_messages=("clone refused by warehouse",),
            expected_error_fragment="refusing to adopt a stage of unknown completeness",
            expected_stage_exists=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_clone_failure_when_creating_stage_then_raises_without_copy(
    test_case: CloneFailureTestCase,
) -> None:
    """Only clean, recognized refusals fall back; anything else surfaces to the caller."""

    adapter: CloneRefusingDuckDbAdapter = CloneRefusingDuckDbAdapter(
        clone_statements=test_case.clone_statements, refused_messages=test_case.refused_messages
    )
    connection: Any = adapter.connect({"database": ":memory:"})
    _ = adapter.execute(
        connection=connection, sql="CREATE TABLE main.orders AS SELECT * FROM range(2) t(id)"
    )
    names: MigrationArtifactNames = artifact_names_for(stage_name=_STAGE)

    with pytest.raises(Exception, match=test_case.expected_error_fragment):
        _ = create_stage(
            adapter=adapter, connection=connection, entry=orders_migration_entry(), names=names
        )

    stage_rows: list[tuple[object, ...]] = adapter.execute(
        connection=connection,
        sql=(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = 'main' AND table_name = '{_STAGE}'"
        ),
    ).fetchall()
    assert bool(stage_rows) is test_case.expected_stage_exists


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
