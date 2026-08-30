"""Conditional DuckDB virtual-environment publication."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.virtual.state._helpers.state_storage.validation import (
    validate_conditional_virtual_environment_publication,
)
from sqlbuild.virtual.state.constants import (
    LOCK_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
)
from sqlbuild.virtual.state.models import (
    StateLockLease,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)


class DuckDbConditionalPublishMixin:
    """Publish virtual refs in the same transaction that validates lease ownership."""

    def upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        self,
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
        leases: tuple[StateLockLease, ...],
        checkpoint: VirtualEnvironmentCheckpointRecord | None = None,
        checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (),
        checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> bool:
        backend: Any = cast(Any, self)
        validate_conditional_virtual_environment_publication(
            record=record,
            refs_by_node_type=refs_by_node_type,
            checkpoint=checkpoint,
            checkpoint_refs=checkpoint_refs,
            checkpoint_function_refs=checkpoint_function_refs,
            checkpoint_seed_refs=checkpoint_seed_refs,
        )
        connection.execute("BEGIN")
        try:
            lock_table: str = backend._qualified_name(schema=schema, table=LOCK_TABLE)
            lease: StateLockLease
            for lease in leases:
                owned: tuple[Any, ...] | None = connection.execute(
                    f"UPDATE {lock_table} SET updated_at = CURRENT_TIMESTAMP "
                    "WHERE lock_key = ? AND owner_id = ? AND expires_at > CURRENT_TIMESTAMP "
                    "RETURNING lock_key",
                    [lease.lock_key, lease.owner_id],
                ).fetchone()
                if owned is None:
                    connection.execute("ROLLBACK")
                    return False
            backend._upsert_virtual_environment_record(
                connection=connection, schema=schema, record=record
            )
            backend._replace_virtual_environment_node_ref_groups(
                connection=connection,
                schema=schema,
                virtual_environment_name=record.virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )
            if checkpoint is not None:
                self._insert_virtual_environment_checkpoint_rows(
                    connection=connection,
                    schema=schema,
                    checkpoint=checkpoint,
                    refs=checkpoint_refs,
                    function_refs=checkpoint_function_refs,
                    seed_refs=checkpoint_seed_refs,
                )
            connection.execute("COMMIT")
            return True
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def _insert_virtual_environment_checkpoint_rows(
        self,
        *,
        connection: Any,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
    ) -> None:
        backend: Any = cast(Any, self)
        checkpoint_table: str = backend._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE
        )
        model_ref_table: str = backend._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE
        )
        function_ref_table: str = backend._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE
        )
        seed_ref_table: str = backend._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE
        )
        connection.execute(
            f"INSERT INTO {checkpoint_table} "
            "(checkpoint_id, virtual_environment_name, created_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            [checkpoint.checkpoint_id, checkpoint.virtual_environment_name],
        )
        ref: VirtualEnvironmentCheckpointModelRefRecord
        for ref in refs:
            connection.execute(
                f"INSERT INTO {model_ref_table} "
                "(checkpoint_id, model_name, version_hash) VALUES (?, ?, ?)",
                [ref.checkpoint_id, ref.model_name, ref.version_hash],
            )
        function_ref: VirtualEnvironmentCheckpointFunctionRefRecord
        for function_ref in function_refs:
            connection.execute(
                f"INSERT INTO {function_ref_table} "
                "(checkpoint_id, function_name, version_hash) VALUES (?, ?, ?)",
                [function_ref.checkpoint_id, function_ref.function_name, function_ref.version_hash],
            )
        seed_ref: VirtualEnvironmentCheckpointSeedRefRecord
        for seed_ref in seed_refs:
            connection.execute(
                f"INSERT INTO {seed_ref_table} "
                "(checkpoint_id, seed_name, version_hash) VALUES (?, ?, ?)",
                [seed_ref.checkpoint_id, seed_ref.seed_name, seed_ref.version_hash],
            )
