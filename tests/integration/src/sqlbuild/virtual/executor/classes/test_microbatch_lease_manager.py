"""Integration coverage for renewable virtual microbatch leases."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.virtual.executor.classes import microbatch_lease_manager as lease_manager_module
from sqlbuild.virtual.executor.classes.microbatch_lease_manager import (
    VirtualMicrobatchLeaseManager,
)
from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.models import StateLockRecord
from tests.integration.src.sqlbuild.virtual.executor.classes._test_types import (
    VirtualMicrobatchLeaseManagerTestCase,
)
from tests.integration.src.sqlbuild.virtual.executor.classes.helpers import (
    build_virtual_microbatch_lease_entry,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualMicrobatchLeaseManagerTestCase(
            description="renewal followed by owner loss fences target mutation",
            renew_interval_seconds=0.02,
            expected_loss_fragment="lease was lost; refusing further target DML",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_renewable_lease_when_owner_is_replaced_then_manager_fences_and_preserves_new_owner(
    test_case: VirtualMicrobatchLeaseManagerTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path: Path = tmp_path / "state.duckdb"
    connection_config: dict[str, object] = {"database": str(state_path)}
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect(connection_config)
    backend.initialize(
        connection=connection,
        schema="sqlbuild_state",
        sqlbuild_version="0.0.test",
    )
    backend.close(connection)
    monkeypatch.setattr(
        lease_manager_module,
        "_LEASE_RENEW_INTERVAL_SECONDS",
        test_case.renew_interval_seconds,
    )
    manager: VirtualMicrobatchLeaseManager = VirtualMicrobatchLeaseManager(
        backend=backend,
        connection_config=connection_config,
        warehouse_connection_config={"database": "warehouse.duckdb"},
        schema="sqlbuild_state",
        run_id="lease-renewal-test",
    )
    manager.acquire(
        entries=(build_virtual_microbatch_lease_entry(),),
        expected_version_hashes={"orders": "F2"},
    )

    connection = backend.connect(connection_config)
    try:
        initial_lock: StateLockRecord = backend.list_active_locks(
            connection=connection,
            schema="sqlbuild_state",
        )[0]
    finally:
        backend.close(connection)
    renewal_deadline: float = time.monotonic() + 2.0
    renewed_lock: StateLockRecord = initial_lock
    while (
        renewed_lock.expires_at <= initial_lock.expires_at and time.monotonic() < renewal_deadline
    ):
        time.sleep(test_case.renew_interval_seconds)
        connection = backend.connect(connection_config)
        try:
            renewed_lock = backend.list_active_locks(
                connection=connection,
                schema="sqlbuild_state",
            )[0]
        finally:
            backend.close(connection)
    assert renewed_lock.expires_at > initial_lock.expires_at

    monkeypatch.setattr(backend, "renew_lock", lambda **_kwargs: False)

    loss_deadline: float = time.monotonic() + 2.0
    loss_error: ExecutorInputError | None = None
    while loss_error is None and time.monotonic() < loss_deadline:
        time.sleep(test_case.renew_interval_seconds)
        try:
            manager.assert_active()
        except ExecutorInputError as error:
            loss_error = error
    assert loss_error is not None
    assert test_case.expected_loss_fragment in str(loss_error)

    connection = backend.connect(connection_config)
    try:
        assert backend.release_lock(
            connection=connection,
            schema="sqlbuild_state",
            lock_key=renewed_lock.lock_key,
            owner_id=renewed_lock.owner_id,
        )
        assert backend.acquire_lock(
            connection=connection,
            schema="sqlbuild_state",
            lock_key=renewed_lock.lock_key,
            owner_id="replacement-owner",
            expires_at=datetime.now() + timedelta(hours=1),
        )
    finally:
        backend.close(connection)

    manager.close()
    connection = backend.connect(connection_config)
    try:
        remaining_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema="sqlbuild_state",
        )
    finally:
        backend.close(connection)
    assert len(remaining_locks) == 1
    assert remaining_locks[0].owner_id == "replacement-owner"


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
