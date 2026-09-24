"""Tests for direct-mode janitor archive planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import chain

import pytest

from sqlbuild.executor.janitor.constants import MALFORMED_ARCHIVE_REASON
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorArchivedRelation,
    JanitorDirectModeSettings,
    JanitorPlan,
    JanitorRelationKey,
    JanitorSkippedRelation,
)
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorArchivePlanTestCase,
    relation_info,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FakeJanitorAdapter,
    build_project,
)

OLD_TIME: datetime = datetime.now(UTC) - timedelta(days=30)
RECENT_ARCHIVE_NAME: str = (
    f"_SQB_ARCHIVE__{(datetime.now(UTC) - timedelta(days=1)):%Y%m%dT%H%M%SZ}__old_customers"
)
LONG_ORDERS_NAME: str = "orders_" + "x" * 60


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorArchivePlanTestCase(
            description="stale relation is archived and kept until archive retention",
            relation_infos=(relation_info("old_orders", created_at=OLD_TIME),),
            expected_archive_source_names=("old_orders",),
        ),
        JanitorArchivePlanTestCase(
            description="zero archive retention deletes the new archive in the same run",
            relation_infos=(relation_info("old_orders"),),
            retention_days=0,
            archive_retention_days=0,
            expected_archive_source_names=("old_orders",),
            expected_same_run_deletion_source_names=("old_orders",),
        ),
        JanitorArchivePlanTestCase(
            description="expired archive is deleted and recent archive is retained",
            relation_infos=(
                relation_info("_SQB_ARCHIVE__20200101T000000Z__old_products"),
                relation_info(RECENT_ARCHIVE_NAME),
            ),
            expected_existing_archive_deletion_names=(
                "_SQB_ARCHIVE__20200101T000000Z__old_products",
            ),
            expected_retained_archive_names=(RECENT_ARCHIVE_NAME,),
        ),
        JanitorArchivePlanTestCase(
            description="case-folded archive name is recognized by strict grammar",
            relation_infos=(relation_info("_sqb_archive__20200101t000000z__old_products"),),
            expected_existing_archive_deletion_names=(
                "_sqb_archive__20200101t000000z__old_products",
            ),
        ),
        JanitorArchivePlanTestCase(
            description="malformed archive look-alikes are reported and never archived or deleted",
            relation_infos=(
                relation_info("_SQB_ARCHIVE__20201399T000000Z__orders", created_at=OLD_TIME),
                relation_info("_SQB_ARCHIVE_20200101T000000Z__orders", created_at=OLD_TIME),
                relation_info("_SQB_ARCHIVE__2020010T000000Z__orders", created_at=OLD_TIME),
                relation_info("_SQB_ARCHIVE__20200101T000000Z__", created_at=OLD_TIME),
                relation_info("_sqb_archive_notes", created_at=OLD_TIME),
            ),
            retention_days=0,
            archive_retention_days=0,
            expected_skipped_relations=(
                ("_SQB_ARCHIVE__20201399T000000Z__orders", MALFORMED_ARCHIVE_REASON),
                ("_SQB_ARCHIVE_20200101T000000Z__orders", MALFORMED_ARCHIVE_REASON),
                ("_SQB_ARCHIVE__2020010T000000Z__orders", MALFORMED_ARCHIVE_REASON),
                ("_SQB_ARCHIVE__20200101T000000Z__", MALFORMED_ARCHIVE_REASON),
                ("_sqb_archive_notes", MALFORMED_ARCHIVE_REASON),
            ),
        ),
        JanitorArchivePlanTestCase(
            description="archive matching an exclude pattern is skipped",
            relation_infos=(relation_info("_SQB_ARCHIVE__20200101T000000Z__keep_orders"),),
            exclude_patterns=("*keep_*",),
            expected_skipped_relations=(
                (
                    "_SQB_ARCHIVE__20200101T000000Z__keep_orders",
                    "relation matches exclude pattern '*keep_*'",
                ),
            ),
        ),
        JanitorArchivePlanTestCase(
            description="blocked schema suppresses expired archive deletion",
            relation_infos=(relation_info("_SQB_ARCHIVE__20200101T000000Z__old_products"),),
            source_schema="analytics",
            expected_suppressed_archive_deletion_names=(
                "_SQB_ARCHIVE__20200101T000000Z__old_products",
            ),
        ),
        JanitorArchivePlanTestCase(
            description="virtual mode neither archives nor expires archive-named relations",
            relation_infos=(
                relation_info("old_orders", created_at=OLD_TIME),
                relation_info("_SQB_ARCHIVE__20200101T000000Z__old_products", created_at=OLD_TIME),
            ),
            direct_mode=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_direct_warehouse_when_planning_janitor_then_plans_archives_by_strict_name(
    test_case: JanitorArchivePlanTestCase,
) -> None:
    adapter: FakeJanitorAdapter = FakeJanitorAdapter(
        relation_infos=test_case.relation_infos,
        identifier_limit=test_case.identifier_limit,
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(source_schema=test_case.source_schema),
        adapter=adapter,
        connection=object(),
        retention_days=test_case.retention_days,
        delete_tracked_only=False,
        exclude_patterns=test_case.exclude_patterns,
        direct_settings=JanitorDirectModeSettings(
            enabled=test_case.direct_mode,
            archive_retention_days=test_case.archive_retention_days,
        ),
    )

    assert (
        tuple(candidate.key.name for candidate in plan.archive_candidates)
        == test_case.expected_archive_source_names
    )
    existing_deletions: tuple[JanitorArchivedRelation, ...] = tuple(
        filter(lambda archive: archive.original_key is None, plan.archive_deletion_candidates)
    )
    same_run_original_keys: tuple[JanitorRelationKey, ...] = tuple(
        filter(None, (archive.original_key for archive in plan.archive_deletion_candidates))
    )
    assert (
        tuple(archive.key.name for archive in existing_deletions)
        == test_case.expected_existing_archive_deletion_names
    )
    assert (
        tuple(key.name for key in same_run_original_keys)
        == test_case.expected_same_run_deletion_source_names
    )
    assert (
        tuple(archive.key.name for archive in plan.retained_archives)
        == test_case.expected_retained_archive_names
    )
    archive_skipped: tuple[JanitorSkippedRelation, ...] = tuple(
        filter(
            lambda skipped: skipped.key.name.lower().startswith("_sqb_archive"),
            plan.skipped_relations,
        )
    )
    assert (
        tuple((skipped.key.name, skipped.reason) for skipped in archive_skipped)
        == test_case.expected_skipped_relations
    )
    suppressed: tuple[JanitorArchivedRelation, ...] = tuple(
        chain.from_iterable(
            blocked.suppressed_archive_deletions for blocked in plan.blocked_schemas
        )
    )
    assert (
        tuple(archive.key.name for archive in suppressed)
        == test_case.expected_suppressed_archive_deletion_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorArchivePlanTestCase(
            description="long relation name is fitted with the archive timestamp intact",
            relation_infos=(relation_info(LONG_ORDERS_NAME, created_at=OLD_TIME),),
            identifier_limit=48,
            expected_archive_source_names=(LONG_ORDERS_NAME,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_long_relation_name_when_planning_archive_then_fits_name_with_timestamp_intact(
    test_case: JanitorArchivePlanTestCase,
) -> None:
    adapter: FakeJanitorAdapter = FakeJanitorAdapter(
        relation_infos=test_case.relation_infos,
        identifier_limit=test_case.identifier_limit,
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(),
        adapter=adapter,
        connection=object(),
        retention_days=test_case.retention_days,
        delete_tracked_only=False,
        direct_settings=JanitorDirectModeSettings(enabled=True),
    )

    assert (
        tuple(candidate.key.name for candidate in plan.archive_candidates)
        == test_case.expected_archive_source_names
    )
    archive_name: str = plan.archive_candidates[0].archive_key.name
    expected_prefix: str = (
        f"_SQB_ARCHIVE__{plan.archive_candidates[0].archived_at:%Y%m%dT%H%M%SZ}__orders_"
    )
    assert len(archive_name) == test_case.identifier_limit
    assert archive_name.startswith(expected_prefix)
    assert archive_name != f"{expected_prefix[:-7]}{LONG_ORDERS_NAME}"


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
