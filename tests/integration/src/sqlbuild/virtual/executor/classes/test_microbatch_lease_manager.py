"""Integration coverage for renewable virtual microbatch leases."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalMode, PlanAction
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.virtual.executor.classes import microbatch_lease_manager as lease_manager_module
from sqlbuild.virtual.executor.classes.microbatch_lease_manager import (
    VirtualMicrobatchLeaseManager,
)
from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateLockRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType, VirtualEnvironmentStatus
from tests.integration.src.sqlbuild.virtual.executor.classes._test_types import (
    VirtualConcurrentLeaseTestCase,
    VirtualLeaseCancellationTestCase,
    VirtualMicrobatchLeaseManagerTestCase,
    VirtualSharedFullRefreshTestCase,
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
            expected_loss_fragment="incremental physical-version lease was lost",
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


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSharedFullRefreshTestCase(
            description="append full refresh rejects shared version",
            incremental_strategy="append",
        ),
        VirtualSharedFullRefreshTestCase(
            description="delete insert full refresh rejects shared version",
            incremental_strategy="delete_insert",
        ),
        VirtualSharedFullRefreshTestCase(
            description="merge full refresh rejects shared version",
            incremental_strategy="merge",
        ),
        VirtualSharedFullRefreshTestCase(
            description="microbatch full refresh rejects shared version",
            incremental_strategy="delete_insert",
            incremental_mode=IncrementalMode.MICROBATCH,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shared_incremental_version_when_full_refresh_then_rejects_immutable_overwrite(
    test_case: VirtualSharedFullRefreshTestCase,
    tmp_path: Path,
) -> None:
    connection_config: dict[str, object] = {"database": str(tmp_path / "state.duckdb")}
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect(connection_config)
    backend.initialize(connection=connection, schema="sqlbuild_state", sqlbuild_version="0.0.test")
    backend.upsert_physical_relation(
        connection=connection,
        schema="sqlbuild_state",
        record=PhysicalRelationRecord(
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name="orders",
            version_hash="F2",
            database_name=None,
            schema_name="dev__sqb_physical",
            relation_name="orders__v_f2",
            relation_type="table",
        ),
    )
    backend.upsert_virtual_environment(
        connection=connection,
        schema="sqlbuild_state",
        record=VirtualEnvironmentRecord(
            virtual_environment_name="shared",
            status=VirtualEnvironmentStatus.FINALIZED,
        ),
    )
    backend.replace_virtual_environment_model_refs(
        connection=connection,
        schema="sqlbuild_state",
        virtual_environment_name="shared",
        refs=(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name="shared",
                model_name="orders",
                version_hash="F2",
            ),
        ),
    )
    backend.close(connection)
    manager: VirtualMicrobatchLeaseManager = VirtualMicrobatchLeaseManager(
        backend=backend,
        connection_config=connection_config,
        warehouse_connection_config={"database": "warehouse.duckdb"},
        schema="sqlbuild_state",
        run_id="shared-full-refresh-test",
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        manager.acquire(
            entries=(
                build_virtual_microbatch_lease_entry(
                    action=PlanAction.CREATE_TABLE,
                    incremental_strategy=test_case.incremental_strategy,
                    incremental_mode=test_case.incremental_mode,
                ),
            ),
            expected_version_hashes={"orders": "F2"},
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentLeaseTestCase(
            description="merge full refresh serializes physical version mutation",
            incremental_strategy="merge",
            incremental_mode=None,
        ),
        VirtualConcurrentLeaseTestCase(
            description="microbatch full refresh preserves physical version serialization",
            incremental_strategy="delete_insert",
            incremental_mode=IncrementalMode.MICROBATCH,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_concurrent_full_refreshes_when_reference_check_blocks_then_version_lease_serializes(
    test_case: VirtualConcurrentLeaseTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_config: dict[str, object] = {"database": str(tmp_path / "state.duckdb")}
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect(connection_config)
    backend.initialize(connection=connection, schema="sqlbuild_state", sqlbuild_version="0.0.test")
    backend.close(connection)
    manager_a: VirtualMicrobatchLeaseManager = VirtualMicrobatchLeaseManager(
        backend=backend,
        connection_config=connection_config,
        warehouse_connection_config={"database": "warehouse.duckdb"},
        schema="sqlbuild_state",
        run_id="concurrent-a",
    )
    manager_b: VirtualMicrobatchLeaseManager = VirtualMicrobatchLeaseManager(
        backend=backend,
        connection_config=connection_config,
        warehouse_connection_config={"database": "warehouse.duckdb"},
        schema="sqlbuild_state",
        run_id="concurrent-b",
    )
    entry: ModelPlanEntry = build_virtual_microbatch_lease_entry(
        action=PlanAction.CREATE_TABLE,
        incremental_strategy=test_case.incremental_strategy,
        incremental_mode=test_case.incremental_mode,
    )
    reference_check_started: Event = Event()
    allow_reference_check: Event = Event()
    original_reference_check: Callable[..., None] = manager_a._reject_shared_full_refresh

    def _blocked_reference_check(**kwargs: Any) -> None:
        reference_check_started.set()
        assert allow_reference_check.wait(timeout=5.0)
        original_reference_check(**kwargs)

    monkeypatch.setattr(manager_a, "_reject_shared_full_refresh", _blocked_reference_check)
    with ThreadPoolExecutor(max_workers=1) as executor:
        acquire_a: Future[None] = executor.submit(
            manager_a.acquire,
            entries=(entry,),
            expected_version_hashes={"orders": "F2"},
        )
        assert reference_check_started.wait(timeout=5.0)
        with pytest.raises(PlannerInputError, match=test_case.expected_conflict_fragment):
            manager_b.acquire(entries=(entry,), expected_version_hashes={"orders": "F2"})
        allow_reference_check.set()
        acquire_a.result(timeout=5.0)

    manager_a.close()
    manager_b.acquire(entries=(entry,), expected_version_hashes={"orders": "F2"})
    manager_b.close()
    connection = backend.connect(connection_config)
    try:
        remaining_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema="sqlbuild_state",
        )
    finally:
        backend.close(connection)
    assert remaining_locks == ()


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualLeaseCancellationTestCase(
            description="cancellation after fencing releases merge full refresh lease",
            expected_error_type=KeyboardInterrupt,
            expected_remaining_lock_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fenced_full_refresh_when_acquisition_is_cancelled_then_releases_version_lease(
    test_case: VirtualLeaseCancellationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_config: dict[str, object] = {"database": str(tmp_path / "state.duckdb")}
    backend: DuckDbStateBackend = DuckDbStateBackend()
    connection: Any = backend.connect(connection_config)
    backend.initialize(connection=connection, schema="sqlbuild_state", sqlbuild_version="0.0.test")
    backend.close(connection)
    manager: VirtualMicrobatchLeaseManager = VirtualMicrobatchLeaseManager(
        backend=backend,
        connection_config=connection_config,
        warehouse_connection_config={"database": "warehouse.duckdb"},
        schema="sqlbuild_state",
        run_id="cancelled-full-refresh",
    )

    def _cancel_reference_check(**_kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(manager, "_reject_shared_full_refresh", _cancel_reference_check)
    with pytest.raises(test_case.expected_error_type):
        manager.acquire(
            entries=(
                build_virtual_microbatch_lease_entry(
                    action=PlanAction.CREATE_TABLE,
                    incremental_strategy="merge",
                    incremental_mode=None,
                ),
            ),
            expected_version_hashes={"orders": "F2"},
        )
    connection = backend.connect(connection_config)
    try:
        remaining_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema="sqlbuild_state",
        )
    finally:
        backend.close(connection)
    assert len(remaining_locks) == test_case.expected_remaining_lock_count


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
