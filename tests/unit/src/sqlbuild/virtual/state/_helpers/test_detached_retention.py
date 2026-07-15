"""Tests for detached virtual environment retention helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlbuild.virtual.state._helpers.state_lifecycle.detached_retention import (
    build_detached_environment_inspection,
)
from sqlbuild.virtual.state.models import (
    DetachedVirtualEnvironmentInspection,
    VirtualEnvironmentRetentionRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus
from tests.unit.src.sqlbuild.virtual.state._helpers._test_types import (
    DetachedRetentionHelperTestCase,
)
from tests.unit.src.sqlbuild.virtual.state._helpers.helpers import (
    physical_relation_for_test,
    virtual_environment_ref_for_test,
)

NOW: datetime = datetime(2026, 5, 27, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    (
        DetachedRetentionHelperTestCase(
            description="retention zero cleans detached refs immediately and retains active refs",
            retention_days=0,
            expected_cleanup_target_names=("old_detached", "new_detached", "unknown_age"),
            expected_cleanup_relation_names=("orders__v_new", "orders__v_old"),
            expected_retained_relation_names=("orders__v_active",),
        ),
        DetachedRetentionHelperTestCase(
            description="positive retention cleans only detached environments older than retention",
            retention_days=7,
            expected_cleanup_target_names=("old_detached",),
            expected_cleanup_relation_names=("orders__v_old",),
            expected_retained_relation_names=("orders__v_active", "orders__v_new"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_environments_when_inspecting_detached_retention_then_classifies_refs(
    test_case: DetachedRetentionHelperTestCase,
) -> None:
    inspection: DetachedVirtualEnvironmentInspection = build_detached_environment_inspection(
        environments=(
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name="old_detached",
                status=VirtualEnvironmentStatus.DETACHED,
                updated_at=NOW - timedelta(days=10),
            ),
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name="new_detached",
                status=VirtualEnvironmentStatus.DETACHED,
                updated_at=NOW - timedelta(days=2),
            ),
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name="unknown_age",
                status=VirtualEnvironmentStatus.DETACHED,
                updated_at=None,
            ),
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name="active",
                status=VirtualEnvironmentStatus.ACTIVE,
                updated_at=NOW - timedelta(days=20),
            ),
        ),
        refs_by_environment={
            "old_detached": (virtual_environment_ref_for_test("old_detached", "orders", "old"),),
            "new_detached": (virtual_environment_ref_for_test("new_detached", "orders", "new"),),
            "unknown_age": (virtual_environment_ref_for_test("unknown_age", "missing", "missing"),),
            "active": (virtual_environment_ref_for_test("active", "orders", "active"),),
        },
        physical_relations_by_ref={
            ("orders", "old"): physical_relation_for_test("orders__v_old", "old"),
            ("orders", "new"): physical_relation_for_test("orders__v_new", "new"),
            ("orders", "active"): physical_relation_for_test("orders__v_active", "active"),
        },
        retention_days=test_case.retention_days,
        now=NOW,
    )

    assert (
        tuple(
            environment.virtual_environment_name
            for environment in inspection.cleanup_virtual_environments
        )
        == test_case.expected_cleanup_target_names
    )
    assert (
        tuple(relation.relation_name for relation in inspection.cleanup_physical_relations)
        == test_case.expected_cleanup_relation_names
    )
    assert (
        tuple(relation.relation_name for relation in inspection.retained_physical_relations)
        == test_case.expected_retained_relation_names
    )
