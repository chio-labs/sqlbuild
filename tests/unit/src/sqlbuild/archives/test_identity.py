from __future__ import annotations

import pytest

from sqlbuild.archives._helpers.identity import archive_event_id, archive_requirement_id
from sqlbuild.archives.types import ArchiveRecordType
from tests.unit.src.sqlbuild.archives._test_types import ArchiveIdentityTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveIdentityTestCase(
            description="same archive operation",
            operation_kind="table_type_migration",
            target_database="warehouse",
            target_schema="analytics",
            target_name="orders",
            source_physical_generation="generation-1",
            archive_name="__sqb_archive__20260831T142530123456Z__orders",
            expected_stable=True,
            expected_event_types_distinct=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_archive_inputs_when_building_identities_then_results_are_stable(
    test_case: ArchiveIdentityTestCase,
) -> None:
    first: str = archive_requirement_id(
        operation_kind=test_case.operation_kind,
        target_database=test_case.target_database,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        source_physical_generation=test_case.source_physical_generation,
        archive_name=test_case.archive_name,
    )
    second: str = archive_requirement_id(
        operation_kind=test_case.operation_kind,
        target_database=test_case.target_database,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        source_physical_generation=test_case.source_physical_generation,
        archive_name=test_case.archive_name,
    )
    assert (first == second) is test_case.expected_stable
    event_types_distinct: bool = archive_event_id(
        requirement_id=first,
        record_type=ArchiveRecordType.REQUIREMENT,
    ) != archive_event_id(
        requirement_id=first,
        record_type=ArchiveRecordType.COMPLETION,
    )
    assert event_types_distinct is test_case.expected_event_types_distinct
