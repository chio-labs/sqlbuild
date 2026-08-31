from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.archives.main._build_archive_name import build_archive_name
from sqlbuild.archives.main._parse_archive_name import parse_archive_name
from sqlbuild.archives.models import ParsedArchiveName
from tests.unit.src.sqlbuild.archives._test_types import ArchiveNameTestCase, ArchiveParseTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveNameTestCase(
            description="short name preserves timestamp and logical name",
            logical_name="orders",
            archived_at=datetime(2026, 8, 31, 14, 25, 30, 123456, tzinfo=UTC),
            identifier_limit=63,
            expected_name="__sqb_archive__20260831T142530123456Z__orders",
        ),
        ArchiveNameTestCase(
            description="long name is fitted deterministically for Postgres",
            logical_name="race_mart_result_with_a_name_that_exceeds_postgres_identifier_limits",
            archived_at=datetime(2026, 8, 31, 14, 25, 30, 123456, tzinfo=UTC),
            identifier_limit=63,
            expected_name="__sqb_archive__20260831T142530123456Z__race_mart_resul_d6ea75c0",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_archive_inputs_when_building_name_then_returns_fitted_sortable_name(
    test_case: ArchiveNameTestCase,
) -> None:
    actual: str = build_archive_name(
        logical_name=test_case.logical_name,
        archived_at=test_case.archived_at,
        identifier_limit=test_case.identifier_limit,
    )
    assert actual == test_case.expected_name
    assert len(actual.encode()) <= test_case.identifier_limit


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveParseTestCase(
            description="valid archive name",
            name="__sqb_archive__20260831T142530123456Z__orders",
            expected_archived_at=datetime(2026, 8, 31, 14, 25, 30, 123456, tzinfo=UTC),
            expected_logical_name="orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_valid_archive_name_when_parsing_then_recovers_timestamp(
    test_case: ArchiveParseTestCase,
) -> None:
    parsed: ParsedArchiveName | None = parse_archive_name(test_case.name)
    assert parsed is not None
    assert parsed.archived_at == test_case.expected_archived_at
    assert parsed.logical_name == test_case.expected_logical_name
