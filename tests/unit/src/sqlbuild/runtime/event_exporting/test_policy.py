import pytest

from sqlbuild._native import (
    event_export_severity_at_least,
    lifecycle_export_policy_catalog,
    stricter_event_export_severity,
)
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS
from sqlbuild.runtime.event_exporting.types import LifecycleEventKind
from sqlbuild.runtime.observability.constants import LIFECYCLE_EVENT_CATALOG
from sqlbuild.spec.contracts.types import EventExportSeverity
from tests.unit.src.sqlbuild.runtime.event_exporting._test_types import (
    EventExportPolicyTestCase,
    SeverityNarrowingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (EventExportPolicyTestCase("complete canonical mapping", len(LIFECYCLE_EVENT_CATALOG)),),
    ids=lambda case: case.description,
)
def test_given_canonical_catalog_when_building_export_policy_then_every_type_is_mapped_once(
    test_case: EventExportPolicyTestCase,
) -> None:
    policy: dict[str, tuple[str, EventExportSeverity, int]] = lifecycle_export_policy_catalog()
    assert len(policy) == test_case.expected_event_count
    assert policy.keys() == LIFECYCLE_EVENT_CATALOG.keys()
    assert {kind for kind, _, _ in policy.values()} == EVENT_EXPORT_KINDS
    assert policy["invocation_failed"] == ("invocation", EventExportSeverity.ERROR, 3)
    assert policy["resource_attempt_skipped"] == ("resource", EventExportSeverity.INFO, 2)
    assert policy["retry_scheduled"] == ("retry", EventExportSeverity.WARNING, 1)
    assert policy["statement_submitted"] == ("statement", EventExportSeverity.DEBUG, 0)
    assert policy["audit_completed"][:2] == (LifecycleEventKind.AUDIT, EventExportSeverity.INFO)
    assert policy["microbatch_started"][:2] == (
        LifecycleEventKind.MICROBATCH,
        EventExportSeverity.DEBUG,
    )
    assert policy["microbatch_completed"][1] == EventExportSeverity.INFO


@pytest.mark.parametrize(
    "test_case",
    (EventExportPolicyTestCase("typed kind vocabulary is exhaustive", 8),),
    ids=lambda case: case.description,
)
def test_given_lifecycle_catalog_when_deriving_export_dimensions_then_kind_enum_is_exhaustive(
    test_case: EventExportPolicyTestCase,
) -> None:
    policy: dict[str, tuple[str, EventExportSeverity, int]] = lifecycle_export_policy_catalog()

    assert {kind for kind, _, _ in policy.values()} == {kind.value for kind in LifecycleEventKind}
    assert len(LifecycleEventKind) == test_case.expected_event_count


@pytest.mark.parametrize(
    "test_case",
    (
        SeverityNarrowingTestCase("absent optional keeps required", "info", None, "info", True),
        SeverityNarrowingTestCase("stricter optional wins", "info", "error", "error", False),
        SeverityNarrowingTestCase(
            "looser optional is ignored", "warning", "debug", "warning", True
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_severity_minimums_when_narrowing_then_stricter_wins_as_typed_severity(
    test_case: SeverityNarrowingTestCase,
) -> None:
    narrowed: EventExportSeverity = stricter_event_export_severity(
        first=test_case.first, second=test_case.second
    )

    assert narrowed is EventExportSeverity(test_case.expected_severity)
    assert (
        event_export_severity_at_least(
            severity=test_case.first, minimum=test_case.second or "debug"
        )
        is test_case.expected_first_meets_second
    )
