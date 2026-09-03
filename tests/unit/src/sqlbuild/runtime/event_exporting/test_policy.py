from collections.abc import Mapping

import pytest

from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS
from sqlbuild.runtime.event_exporting.main._lifecycle_export_policy_catalog import (
    lifecycle_export_policy_catalog,
)
from sqlbuild.runtime.event_exporting.models import LifecycleExportPolicy
from sqlbuild.runtime.observability.constants import LIFECYCLE_EVENT_CATALOG
from tests.unit.src.sqlbuild.runtime.event_exporting._test_types import (
    EventExportPolicyTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (EventExportPolicyTestCase("complete canonical mapping", len(LIFECYCLE_EVENT_CATALOG)),),
    ids=lambda case: case.description,
)
def test_given_canonical_catalog_when_building_export_policy_then_every_type_is_mapped_once(
    test_case: EventExportPolicyTestCase,
) -> None:
    policy: Mapping[str, LifecycleExportPolicy] = lifecycle_export_policy_catalog()
    assert len(policy) == test_case.expected_event_count
    assert policy.keys() == LIFECYCLE_EVENT_CATALOG.keys()
    assert {item.kind for item in policy.values()} == EVENT_EXPORT_KINDS
    assert policy["invocation_failed"].severity == "error"
    assert policy["resource_attempt_skipped"].severity == "info"
    assert policy["retry_scheduled"].severity == "warning"
    assert policy["statement_submitted"].severity == "debug"
