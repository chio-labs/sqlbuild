from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sqlbuild.virtual.state.helpers.locks import (
    acquire_model_version_lock,
    acquire_state_migration_lock,
    acquire_virtual_environment_lock,
    release_state_lock,
)
from sqlbuild.virtual.state.models import StateLockLease
from tests.unit.src.sqlbuild.virtual.state.helpers._test_types import (
    StateLockServiceTestCase,
)
from tests.unit.src.sqlbuild.virtual.state.helpers.helpers import FakeStateBackend


@pytest.mark.parametrize(
    "test_case",
    [
        StateLockServiceTestCase(
            description="builds scoped lock keys and returns leases when acquired",
            schema="sqlbuild_state",
            owner_id="run-1",
            now=datetime(2026, 5, 25, 12, 0, 0),
            ttl=timedelta(minutes=15),
            expected_virtual_environment_lock_key="virtual_env:dev",
            expected_model_version_lock_key="model_version:fact_orders:abc123",
            expected_state_migration_lock_key="state_migration",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_state_lock_service_when_acquiring_scoped_locks_then_uses_expected_lock_keys(
    test_case: StateLockServiceTestCase,
) -> None:
    backend: FakeStateBackend = FakeStateBackend(acquire_result=True)
    connection: object = object()

    virtual_environment_lease: StateLockLease | None = acquire_virtual_environment_lock(
        backend,
        connection,
        schema=test_case.schema,
        virtual_environment_name="dev",
        owner_id=test_case.owner_id,
        ttl=test_case.ttl,
        now=test_case.now,
    )
    model_version_lease: StateLockLease | None = acquire_model_version_lock(
        backend,
        connection,
        schema=test_case.schema,
        model_name="fact_orders",
        version_hash="abc123",
        owner_id=test_case.owner_id,
        ttl=test_case.ttl,
        now=test_case.now,
    )
    state_migration_lease: StateLockLease | None = acquire_state_migration_lock(
        backend,
        connection,
        schema=test_case.schema,
        owner_id=test_case.owner_id,
        ttl=test_case.ttl,
        now=test_case.now,
    )

    assert virtual_environment_lease is not None
    assert model_version_lease is not None
    assert state_migration_lease is not None
    assert virtual_environment_lease.lock_key == test_case.expected_virtual_environment_lock_key
    assert model_version_lease.lock_key == test_case.expected_model_version_lock_key
    assert state_migration_lease.lock_key == test_case.expected_state_migration_lock_key
    assert virtual_environment_lease.expires_at == test_case.now + test_case.ttl
    assert tuple(call[0] for call in backend.acquire_calls) == (
        test_case.expected_virtual_environment_lock_key,
        test_case.expected_model_version_lock_key,
        test_case.expected_state_migration_lock_key,
    )
    assert release_state_lock(
        backend,
        connection,
        schema=test_case.schema,
        lease=virtual_environment_lease,
    )
    assert backend.release_calls == [
        (test_case.expected_virtual_environment_lock_key, test_case.owner_id)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        StateLockServiceTestCase(
            description="returns no lease when backend lock acquisition conflicts",
            schema="sqlbuild_state",
            owner_id="run-1",
            now=datetime(2026, 5, 25, 12, 0, 0),
            ttl=timedelta(minutes=15),
            expected_virtual_environment_lock_key="virtual_env:dev",
            expected_model_version_lock_key="model_version:fact_orders:abc123",
            expected_state_migration_lock_key="state_migration",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_state_lock_service_when_backend_reports_conflict_then_returns_none(
    test_case: StateLockServiceTestCase,
) -> None:
    backend: FakeStateBackend = FakeStateBackend(acquire_result=False)
    connection: object = object()

    lease: StateLockLease | None = acquire_virtual_environment_lock(
        backend,
        connection,
        schema=test_case.schema,
        virtual_environment_name="dev",
        owner_id=test_case.owner_id,
        ttl=test_case.ttl,
        now=test_case.now,
    )

    assert lease is None
    assert backend.acquire_calls == [
        (
            test_case.expected_virtual_environment_lock_key,
            test_case.owner_id,
            test_case.now + test_case.ttl,
        )
    ]
