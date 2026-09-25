"""Tests for staged-relation promotion shared by full refresh and model migrations."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.run._helpers.materializations.full_refresh import (
    promote_full_refresh_rebuild,
    resolve_full_refresh_relations,
)
from sqlbuild.executor.run.main.promote_staged_relation import promote_staged_relation
from sqlbuild.executor.run.models import FullRefreshRelations
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    FullRefreshPromotionTestCase,
    StagedPromotionTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import (
    RecordingConnection,
    build_recording_adapter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StagedPromotionTestCase(
            description="missing target is promoted by renaming the stage",
            adapter_name="duckdb",
            target_exists=False,
            expected_statements=("ALTER TABLE main.orders_stage RENAME TO orders",),
        ),
        StagedPromotionTestCase(
            description="rename adapters move the live target aside before renaming the stage",
            adapter_name="postgres",
            target_exists=True,
            expected_statements=(
                "ALTER TABLE main.orders RENAME TO orders_previous",
                "ALTER TABLE main.orders_stage RENAME TO orders",
            ),
        ),
        StagedPromotionTestCase(
            description="snowflake swaps then keeps the displaced target under the displaced name",
            adapter_name="snowflake",
            target_exists=True,
            expected_statements=(
                "ALTER TABLE main.orders SWAP WITH main.orders_stage",
                "ALTER TABLE main.orders_stage RENAME TO main.orders_previous",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_staged_relation_when_promoting_then_nothing_is_dropped(
    test_case: StagedPromotionTestCase,
) -> None:
    """Promotion never drops the live target or the stage."""

    adapter: BaseAdapter = build_recording_adapter(test_case.adapter_name)
    connection: RecordingConnection = RecordingConnection()

    promote_staged_relation(
        adapter=adapter,
        connection=connection,
        target_qualified="main.orders",
        staged_qualified="main.orders_stage",
        displaced_qualified="main.orders_previous",
        target_exists=test_case.target_exists,
        statement_recorder=StatementRecorder(),
    )

    assert tuple(connection.executed) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        FullRefreshPromotionTestCase(
            description="first full refresh renames the rebuild into place",
            adapter_name="duckdb",
            target_exists=False,
            expected_statements=("ALTER TABLE main.__sqb_rebuild__orders RENAME TO orders",),
        ),
        FullRefreshPromotionTestCase(
            description="rename adapters drop the previous copy then rename twice",
            adapter_name="duckdb",
            target_exists=True,
            expected_statements=(
                "DROP TABLE IF EXISTS main.__sqb_prev__orders",
                "ALTER TABLE main.orders RENAME TO __sqb_prev__orders",
                "ALTER TABLE main.__sqb_rebuild__orders RENAME TO orders",
            ),
        ),
        FullRefreshPromotionTestCase(
            description="snowflake drops the previous copy then swaps",
            adapter_name="snowflake",
            target_exists=True,
            expected_statements=(
                "DROP TABLE IF EXISTS main.__sqb_prev__orders",
                "DROP VIEW IF EXISTS main.__sqb_prev__orders",
                "ALTER TABLE main.orders SWAP WITH main.__sqb_rebuild__orders",
                "ALTER TABLE main.__sqb_rebuild__orders RENAME TO main.__sqb_prev__orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_full_refresh_rebuild_when_promoting_then_statements_are_unchanged(
    test_case: FullRefreshPromotionTestCase,
) -> None:
    """Full refresh keeps its drop-previous-then-promote sequence."""

    adapter: BaseAdapter = build_recording_adapter(test_case.adapter_name)
    connection: RecordingConnection = RecordingConnection()
    relations: FullRefreshRelations = resolve_full_refresh_relations(
        adapter=adapter, database=None, schema="main", target_name="orders"
    )

    promote_full_refresh_rebuild(
        adapter=adapter,
        connection=connection,
        relations=relations,
        target_exists=test_case.target_exists,
        statement_recorder=StatementRecorder(),
    )

    assert tuple(connection.executed) == test_case.expected_statements
