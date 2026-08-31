from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.main._project_archive_events import project_archive_events
from sqlbuild.archives.models import ArchiveProjection
from sqlbuild.archives.types import ArchiveRecordType
from tests.unit.src.sqlbuild.archives._test_types import (
    ArchiveConflictTestCase,
    ArchiveProjectionTestCase,
)
from tests.unit.src.sqlbuild.archives.helpers import archive_event


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveProjectionTestCase(
            description="requirement remains pending",
            events=(
                archive_event(event_id="requirement", record_type=ArchiveRecordType.REQUIREMENT),
            ),
            expected_available=False,
            expected_deleted=False,
            expected_completion_event_id=None,
        ),
        ArchiveProjectionTestCase(
            description="out of order completion projects available",
            events=(
                archive_event(
                    event_id="completion",
                    record_type=ArchiveRecordType.COMPLETION,
                    created_at=datetime(2026, 8, 31, 14, 25, 31, tzinfo=UTC),
                ),
                archive_event(event_id="requirement", record_type=ArchiveRecordType.REQUIREMENT),
            ),
            expected_available=True,
            expected_deleted=False,
            expected_completion_event_id="completion",
        ),
        ArchiveProjectionTestCase(
            description="delete completion projects deleted",
            events=(
                archive_event(event_id="requirement", record_type=ArchiveRecordType.REQUIREMENT),
                archive_event(event_id="completion", record_type=ArchiveRecordType.COMPLETION),
                archive_event(
                    event_id="delete-requirement",
                    record_type=ArchiveRecordType.DELETE_REQUIREMENT,
                ),
                archive_event(
                    event_id="delete-completion",
                    record_type=ArchiveRecordType.DELETE_COMPLETION,
                ),
            ),
            expected_available=False,
            expected_deleted=True,
            expected_completion_event_id="completion",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_archive_events_when_projecting_then_returns_expected_lifecycle(
    test_case: ArchiveProjectionTestCase,
) -> None:
    projection: ArchiveProjection = project_archive_events(test_case.events)
    assert projection.is_available is test_case.expected_available
    assert projection.is_deleted is test_case.expected_deleted
    actual_completion_id: str | None = getattr(projection.completion, "event_id", None)
    assert actual_completion_id == test_case.expected_completion_event_id


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveConflictTestCase(
            description="same event ID with different payload",
            events=(
                archive_event(event_id="duplicate", record_type=ArchiveRecordType.REQUIREMENT),
                archive_event(event_id="duplicate", record_type=ArchiveRecordType.COMPLETION),
            ),
            expected_error_fragment="conflicting payloads",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_duplicate_event_when_projecting_then_fails_closed(
    test_case: ArchiveConflictTestCase,
) -> None:
    with pytest.raises(ArchiveStateError, match=test_case.expected_error_fragment):
        project_archive_events(test_case.events)
