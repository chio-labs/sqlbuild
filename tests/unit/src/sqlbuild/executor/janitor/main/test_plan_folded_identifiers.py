"""Janitor planning against warehouses that report folded identifier case."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from itertools import chain

import pytest

from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorDirectModeSettings,
    JanitorPlan,
    JanitorRelationKey,
    JanitorRelationScope,
)
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorFoldedIdentifierPlanTestCase,
    relation_info,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FoldingJanitorAdapter,
    build_project,
)

OLD_TIME: datetime = datetime.now(UTC) - timedelta(days=30)
ARCHIVE_TIMESTAMP_RE: re.Pattern[str] = re.compile(r"__[0-9]{8}t[0-9]{6}z__")


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorFoldedIdentifierPlanTestCase(
            description="lowercase listing finds stale relation and protects desired relations",
            relation_infos=(
                relation_info(
                    "orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
                relation_info(
                    "countries", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
                relation_info(
                    "old_orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
            ),
            expected_candidate_display_names=("ANALYTICS.DEV_ORDERS.old_orders",),
            expected_archive_display_names=("ANALYTICS.DEV_ORDERS._sqb_archive__<ts>__old_orders",),
        ),
        JanitorFoldedIdentifierPlanTestCase(
            description="tracked-only filter matches fingerprints across identifier case",
            relation_infos=(
                relation_info(
                    "old_orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
                relation_info(
                    "stray_orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
            ),
            delete_tracked_only=True,
            tracked_relations=(("ANALYTICS", "DEV_ORDERS", "OLD_ORDERS"),),
            expected_candidate_display_names=("ANALYTICS.DEV_ORDERS.old_orders",),
            expected_archive_display_names=("ANALYTICS.DEV_ORDERS._sqb_archive__<ts>__old_orders",),
            expected_skipped_relations=(
                ("ANALYTICS.DEV_ORDERS.stray_orders", "relation is not tracked by SQLBuild"),
                (
                    "ANALYTICS.DEV_ORDERS._sqlbuild_fingerprints",
                    "relation matches exclude pattern '_sqlbuild_fingerprints'",
                ),
            ),
        ),
        JanitorFoldedIdentifierPlanTestCase(
            description="sources in a different schema of the same database do not block",
            relation_infos=(
                relation_info(
                    "old_orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
            ),
            source_database="ANALYTICS",
            source_schema="RAW",
            expected_candidate_display_names=("ANALYTICS.DEV_ORDERS.old_orders",),
            expected_archive_display_names=("ANALYTICS.DEV_ORDERS._sqb_archive__<ts>__old_orders",),
        ),
        JanitorFoldedIdentifierPlanTestCase(
            description="source in the managed schema blocks even when spelled differently",
            relation_infos=(
                relation_info(
                    "old_orders", database="ANALYTICS", schema="DEV_ORDERS", created_at=OLD_TIME
                ),
            ),
            source_database="analytics",
            source_schema="dev_orders",
            expected_blocked_sources=("raw_orders",),
            expected_suppressed_names=("ANALYTICS.DEV_ORDERS.old_orders",),
        ),
        JanitorFoldedIdentifierPlanTestCase(
            description="expired archive is found in a lowercase listing",
            relation_infos=(
                relation_info(
                    "_sqb_archive__20200101t000000z__old_products",
                    database="ANALYTICS",
                    schema="DEV_ORDERS",
                ),
            ),
            expected_archive_deletion_display_names=(
                "ANALYTICS.DEV_ORDERS._sqb_archive__20200101t000000z__old_products",
            ),
        ),
        JanitorFoldedIdentifierPlanTestCase(
            description="virtual protection matches physical relations across identifier case",
            relation_infos=(
                relation_info(
                    "orders__v1",
                    database="ANALYTICS",
                    schema="DEV_ORDERS__SQB_PHYSICAL",
                    created_at=OLD_TIME,
                ),
                relation_info(
                    "orders__v0",
                    database="ANALYTICS",
                    schema="DEV_ORDERS__SQB_PHYSICAL",
                    created_at=OLD_TIME,
                ),
            ),
            direct_mode=False,
            protected_relation_keys=frozenset(
                (
                    JanitorRelationKey(
                        database="ANALYTICS",
                        schema="DEV_ORDERS__SQB_PHYSICAL",
                        name="ORDERS__V1",
                    ),
                )
            ),
            expected_candidate_display_names=("ANALYTICS.DEV_ORDERS__SQB_PHYSICAL.orders__v0",),
            expected_skipped_relations=(
                (
                    "ANALYTICS.DEV_ORDERS__SQB_PHYSICAL.orders__v1",
                    "relation is referenced by a retained virtual checkpoint",
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_folded_catalog_identifiers_when_planning_janitor_then_keys_compare_consistently(
    test_case: JanitorFoldedIdentifierPlanTestCase,
) -> None:
    adapter: FoldingJanitorAdapter = FoldingJanitorAdapter(
        relation_infos=test_case.relation_infos,
        tracked_relations=test_case.tracked_relations,
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(
            source_database=test_case.source_database,
            source_schema=test_case.source_schema,
            destination_database="ANALYTICS",
            destination_schema="DEV_ORDERS",
        ),
        adapter=adapter,
        connection=object(),
        retention_days=7,
        delete_tracked_only=test_case.delete_tracked_only,
        relation_scope=JanitorRelationScope(
            protected_relation_keys=test_case.protected_relation_keys
        ),
        direct_settings=JanitorDirectModeSettings(enabled=test_case.direct_mode),
    )

    assert (
        tuple(candidate.key.display_name() for candidate in plan.candidates)
        == test_case.expected_candidate_display_names
    )
    assert (
        tuple(
            ARCHIVE_TIMESTAMP_RE.sub("__<ts>__", candidate.archive_key.display_name())
            for candidate in plan.archive_candidates
        )
        == test_case.expected_archive_display_names
    )
    assert (
        tuple(archive.key.display_name() for archive in plan.archive_deletion_candidates)
        == test_case.expected_archive_deletion_display_names
    )
    assert (
        tuple((skipped.key.display_name(), skipped.reason) for skipped in plan.skipped_relations)
        == test_case.expected_skipped_relations
    )
    blocked_sources: tuple[str, ...] = tuple(
        chain.from_iterable(blocked.source_names for blocked in plan.blocked_schemas)
    )
    suppressed: tuple[JanitorDeleteCandidate, ...] = tuple(
        chain.from_iterable(blocked.suppressed_candidates for blocked in plan.blocked_schemas)
    )
    assert blocked_sources == test_case.expected_blocked_sources
    assert (
        tuple(candidate.key.display_name() for candidate in suppressed)
        == test_case.expected_suppressed_names
    )
