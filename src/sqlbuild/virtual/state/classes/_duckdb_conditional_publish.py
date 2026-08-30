"""Conditional DuckDB virtual-environment publication."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.virtual.state.constants import LOCK_TABLE
from sqlbuild.virtual.state.models import (
    StateLockLease,
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
    ) -> bool:
        backend: Any = cast(Any, self)
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
            connection.execute("COMMIT")
            return True
        except BaseException:
            connection.execute("ROLLBACK")
            raise
