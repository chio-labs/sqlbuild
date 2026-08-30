"""Renewable physical-version lease manager for virtual microbatch mutation."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalMode, MaterializationType, PlanAction
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.locks._model_version_lock import acquire_model_version_lease
from sqlbuild.virtual.state.main.locks._release_lock import release_state_lease
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateLockLease,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRetentionRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType

_LEASE_TTL: timedelta = timedelta(minutes=5)
_LEASE_RENEW_INTERVAL_SECONDS: float = 60.0


class VirtualMicrobatchLeaseManager:
    """Protect shared incremental versions and lease microbatch mutations."""

    def __init__(
        self,
        *,
        backend: StateBackend,
        connection_config: dict[str, object],
        warehouse_connection_config: dict[str, object],
        schema: str,
        run_id: str,
    ) -> None:
        self._backend = backend
        self._connection_config = connection_config
        self._schema = schema
        self._owner_id = f"build:{run_id}"
        self._warehouse_realm = hashlib.sha256(
            json.dumps(warehouse_connection_config, sort_keys=True, default=str).encode()
        ).hexdigest()
        self._leases: tuple[StateLockLease, ...] = ()
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    def acquire(
        self,
        *,
        entries: tuple[ModelPlanEntry, ...],
        expected_version_hashes: dict[str, str],
    ) -> None:
        incremental_entries: tuple[ModelPlanEntry, ...] = tuple(
            entry
            for entry in entries
            if entry.materialization_type == MaterializationType.INCREMENTAL
            and entry.action != PlanAction.SKIP
        )
        lease_entries: tuple[ModelPlanEntry, ...] = tuple(
            entry
            for entry in incremental_entries
            if entry.incremental_mode == IncrementalMode.MICROBATCH
            or entry.action == PlanAction.CREATE_TABLE
        )
        if not lease_entries:
            return
        connection: Any = self._backend.connect(self._connection_config)
        leases: list[StateLockLease] = []
        try:
            entries_by_version: dict[tuple[str, str], ModelPlanEntry] = {}
            for entry in lease_entries:
                version_hash: str = expected_version_hashes.get(
                    entry.name,
                    entry.fingerprint_version_hash
                    or compute_query_hash(entry.fingerprint_query_sql),
                )
                entries_by_version[(entry.name, version_hash)] = entry
            entry_key: tuple[str, str]
            for entry_key in sorted(entries_by_version):
                entry: ModelPlanEntry = entries_by_version[entry_key]
                version_hash = entry_key[1]
                lease: StateLockLease | None = acquire_model_version_lease(
                    backend=self._backend,
                    connection=connection,
                    schema=self._schema,
                    model_name=f"{self._warehouse_realm}:{entry.name}",
                    version_hash=version_hash,
                    owner_id=self._owner_id,
                    ttl=_LEASE_TTL,
                )
                if lease is None:
                    raise PlannerInputError(
                        "virtual incremental physical version is already being mutated: "
                        f"{entry.name}@{version_hash}"
                    )
                leases.append(lease)
            for entry_key in sorted(entries_by_version):
                self._reject_shared_full_refresh(
                    connection=connection,
                    entry=entries_by_version[entry_key],
                    version_hash=entry_key[1],
                )
        except BaseException:
            self._release(connection=connection, leases=tuple(leases))
            raise
        finally:
            self._backend.close(connection)
        self._leases = tuple(leases)
        if not leases:
            return
        self._thread = threading.Thread(
            target=self._renew_until_stopped,
            name=f"sqlbuild-lease-{self._owner_id}",
            daemon=True,
        )
        self._thread.start()

    def assert_active(self) -> None:
        """Fence target DML after a renewal failure or lost owner row."""

        if self._lost.is_set():
            raise ExecutorInputError(
                "virtual incremental physical-version lease was lost; refusing further target DML"
            )

    @property
    def active_leases(self) -> tuple[StateLockLease, ...]:
        """Return the leases that must still be owned when model refs are published."""

        return self._leases

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if not self._leases:
            return
        connection: Any = self._backend.connect(self._connection_config)
        try:
            self._release(connection=connection, leases=self._leases)
        finally:
            self._backend.close(connection)

    def _renew_until_stopped(self) -> None:
        while not self._stop.wait(_LEASE_RENEW_INTERVAL_SECONDS):
            connection: Any = self._backend.connect(self._connection_config)
            try:
                expires_at: datetime = datetime.now() + _LEASE_TTL
                for lease in self._leases:
                    if not self._backend.renew_lock(
                        connection=connection,
                        schema=self._schema,
                        lock_key=lease.lock_key,
                        owner_id=lease.owner_id,
                        expires_at=expires_at,
                    ):
                        self._lost.set()
                        return
            except Exception:
                self._lost.set()
                return
            finally:
                self._backend.close(connection)

    def _release(self, *, connection: Any, leases: tuple[StateLockLease, ...]) -> None:
        for lease in reversed(leases):
            release_state_lease(
                backend=self._backend,
                connection=connection,
                schema=self._schema,
                lease=lease,
            )

    def _reject_shared_full_refresh(
        self, *, connection: Any, entry: ModelPlanEntry, version_hash: str
    ) -> None:
        existing: PhysicalRelationRecord | None = self._backend.get_physical_relation_for_artifact(
            connection=connection,
            schema=self._schema,
            artifact_type=PhysicalArtifactType.MODEL,
            artifact_name=entry.name,
            version_hash=version_hash,
        )
        if (
            entry.action == PlanAction.CREATE_TABLE
            and existing is not None
            and self._model_version_is_referenced(
                connection=connection,
                model_name=entry.name,
                version_hash=version_hash,
            )
        ):
            raise PlannerInputError(
                "virtual incremental full refresh cannot replace a shared physical version: "
                f"{entry.name}@{version_hash}; change the model definition to create a new "
                "immutable version"
            )

    def _model_version_is_referenced(
        self, *, connection: Any, model_name: str, version_hash: str
    ) -> bool:
        environments: tuple[VirtualEnvironmentRetentionRecord, ...] = (
            self._backend.list_virtual_environments(
                connection=connection,
                schema=self._schema,
            )
        )
        for environment in environments:
            refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
                self._backend.get_virtual_environment_model_refs(
                    connection=connection,
                    schema=self._schema,
                    virtual_environment_name=environment.virtual_environment_name,
                )
            )
            if any(
                ref.model_name == model_name and ref.version_hash == version_hash for ref in refs
            ):
                return True
            checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
                self._backend.list_virtual_environment_checkpoints(
                    connection=connection,
                    schema=self._schema,
                    virtual_environment_name=environment.virtual_environment_name,
                )
            )
            for checkpoint in checkpoints:
                checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (
                    self._backend.get_virtual_environment_checkpoint_model_refs(
                        connection=connection,
                        schema=self._schema,
                        checkpoint_id=checkpoint.checkpoint_id,
                    )
                )
                if any(
                    ref.model_name == model_name and ref.version_hash == version_hash
                    for ref in checkpoint_refs
                ):
                    return True
        return False
