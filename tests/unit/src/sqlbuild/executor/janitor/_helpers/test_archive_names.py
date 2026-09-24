from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.executor.janitor._helpers.archive_names import (
    build_archive_name,
    is_archive_lookalike_name,
    parse_archive_name,
)
from sqlbuild.executor.janitor.models import JanitorParsedArchiveName
from tests.unit.src.sqlbuild.executor.janitor._helpers._test_types import (
    ArchiveNameBuildTestCase,
    ArchiveNameParseTestCase,
    ArchiveNameRejectTestCase,
)

ARCHIVED_AT: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)
LONG_NAME: str = "fulfillment_orders_" + "y" * 80


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveNameParseTestCase(
            description="canonical archive name parses",
            name="_SQB_ARCHIVE__20260924T101500Z__orders",
            expected_archived_at=ARCHIVED_AT,
            expected_logical_name="orders",
        ),
        ArchiveNameParseTestCase(
            description="lowercase folded archive name parses",
            name="_sqb_archive__20260924t101500z__orders",
            expected_archived_at=ARCHIVED_AT,
            expected_logical_name="orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_strict_archive_name_when_parsing_then_returns_timestamp_and_logical_name(
    test_case: ArchiveNameParseTestCase,
) -> None:
    parsed: JanitorParsedArchiveName | None = parse_archive_name(test_case.name)

    assert parsed == JanitorParsedArchiveName(
        archived_at=test_case.expected_archived_at,
        logical_name=test_case.expected_logical_name,
    )
    assert is_archive_lookalike_name(test_case.name) is True


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveNameRejectTestCase(
            description="impossible calendar timestamp is malformed",
            name="_SQB_ARCHIVE__20261324T101500Z__orders",
            expected_lookalike=True,
        ),
        ArchiveNameRejectTestCase(
            description="missing timezone marker is malformed",
            name="_SQB_ARCHIVE__20260924T101500__orders",
            expected_lookalike=True,
        ),
        ArchiveNameRejectTestCase(
            description="single separator after prefix is malformed",
            name="_SQB_ARCHIVE_20260924T101500Z__orders",
            expected_lookalike=True,
        ),
        ArchiveNameRejectTestCase(
            description="empty original name is malformed",
            name="_SQB_ARCHIVE__20260924T101500Z__",
            expected_lookalike=True,
        ),
        ArchiveNameRejectTestCase(
            description="ordinary relation is neither archive nor look-alike",
            name="orders_archive",
            expected_lookalike=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_strict_name_when_parsing_archive_name_then_returns_none(
    test_case: ArchiveNameRejectTestCase,
) -> None:
    parsed: JanitorParsedArchiveName | None = parse_archive_name(test_case.name)

    assert parsed is None
    assert is_archive_lookalike_name(test_case.name) is test_case.expected_lookalike


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveNameBuildTestCase(
            description="short name keeps the full original name",
            original_name="orders",
            archived_at=ARCHIVED_AT,
            identifier_limit=255,
            expected_prefix="_SQB_ARCHIVE__20260924T101500Z__orders",
            expected_length=len("_SQB_ARCHIVE__20260924T101500Z__orders"),
            expected_logical_name_is_original=True,
        ),
        ArchiveNameBuildTestCase(
            description="long name is fitted while the timestamp stays intact",
            original_name=LONG_NAME,
            archived_at=ARCHIVED_AT.replace(microsecond=654321),
            identifier_limit=63,
            expected_prefix="_SQB_ARCHIVE__20260924T101500Z__fulfillment_orders_",
            expected_length=63,
            expected_logical_name_is_original=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_original_name_when_building_archive_name_then_round_trips_through_parser(
    test_case: ArchiveNameBuildTestCase,
) -> None:
    archive_name: str = build_archive_name(
        original_name=test_case.original_name,
        archived_at=test_case.archived_at,
        identifier_limit=test_case.identifier_limit,
    )

    parsed: JanitorParsedArchiveName | None = parse_archive_name(archive_name)
    assert archive_name.startswith(test_case.expected_prefix)
    assert len(archive_name) == test_case.expected_length
    assert parsed is not None
    assert parsed.archived_at == ARCHIVED_AT
    assert (parsed.logical_name == test_case.original_name) is (
        test_case.expected_logical_name_is_original
    )
