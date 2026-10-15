from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from sqlbuild._native import build_janitor_archive_name
from tests.unit.src.sqlbuild.executor.janitor._helpers._test_types import (
    ArchiveNameBuildTestCase,
)

ARCHIVED_AT: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)
LONG_NAME: str = "fulfillment_orders_" + "y" * 80
ARCHIVE_NAME_PATTERN: re.Pattern[str] = re.compile(
    r"^_sqb_archive__20260924t101500z__(?P<logical_name>.+)$"
)


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveNameBuildTestCase(
            description="short name keeps the full original name",
            original_name="orders",
            archived_at=ARCHIVED_AT,
            identifier_limit=255,
            expected_prefix="_sqb_archive__20260924t101500z__orders",
            expected_length=len("_sqb_archive__20260924t101500z__orders"),
            expected_logical_name_is_original=True,
        ),
        ArchiveNameBuildTestCase(
            description="long name is fitted while the timestamp stays intact",
            original_name=LONG_NAME,
            archived_at=ARCHIVED_AT.replace(microsecond=654321),
            identifier_limit=63,
            expected_prefix="_sqb_archive__20260924t101500z__fulfillment_orders_",
            expected_length=63,
            expected_logical_name_is_original=False,
        ),
        ArchiveNameBuildTestCase(
            description="kind segment follows the timestamp and precedes the original name",
            original_name="orders",
            archived_at=ARCHIVED_AT,
            identifier_limit=255,
            expected_prefix="_sqb_archive__20260924t101500z__migration_stage__orders",
            expected_length=len("_sqb_archive__20260924t101500z__migration_stage__orders"),
            expected_logical_name_is_original=False,
            kind="migration_stage",
        ),
        ArchiveNameBuildTestCase(
            description="long name is fitted after an intact kind at the postgres limit",
            original_name=LONG_NAME,
            archived_at=ARCHIVED_AT,
            identifier_limit=63,
            expected_prefix="_sqb_archive__20260924t101500z__migration_previous__fu_",
            expected_length=63,
            expected_logical_name_is_original=False,
            kind="migration_previous",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_original_name_when_building_archive_name_then_keeps_timestamp_and_fits(
    test_case: ArchiveNameBuildTestCase,
) -> None:
    archive_name: str = build_janitor_archive_name(
        original_name=test_case.original_name,
        archived_at=test_case.archived_at,
        identifier_limit=test_case.identifier_limit,
        kind=test_case.kind,
    )

    parsed: re.Match[str] | None = ARCHIVE_NAME_PATTERN.fullmatch(archive_name)
    assert archive_name.startswith(test_case.expected_prefix)
    assert len(archive_name) == test_case.expected_length
    assert parsed is not None
    assert (parsed.group("logical_name") == test_case.original_name) is (
        test_case.expected_logical_name_is_original
    )
