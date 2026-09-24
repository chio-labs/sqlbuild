"""Shared SQL fragments for snapshot materializations."""

from __future__ import annotations

from sqlbuild.compiler.planner.types import InitialValidFrom, SnapshotStrategy


class SnapshotSql:
    """Render SQL fragments shared by snapshot materializations."""

    @staticmethod
    def key_condition(*, left_alias: str, right_alias: str, unique_key: tuple[str, ...]) -> str:
        """Render the equality join between two aliases over the snapshot unique key."""

        return " AND ".join(
            f"{left_alias}.{column} = {right_alias}.{column}" for column in unique_key
        )

    @staticmethod
    def initial_valid_from_expr(
        *,
        snapshot_strategy: str | None,
        updated_at_column: str | None,
        observed_at_column: str | None,
        initial_valid_from: str | None,
        source_alias: str | None,
        current_timestamp: str,
    ) -> str:
        """Render the valid_from expression for a key's first snapshot version."""

        prefix: str = f"{source_alias}." if source_alias is not None else ""
        if initial_valid_from == InitialValidFrom.EXECUTION_TIME:
            return current_timestamp
        if initial_valid_from == InitialValidFrom.OBSERVED_AT and observed_at_column is not None:
            return f"{prefix}{observed_at_column}"
        if initial_valid_from == InitialValidFrom.UPDATED_AT and updated_at_column is not None:
            return f"{prefix}{updated_at_column}"
        if snapshot_strategy == SnapshotStrategy.TIMESTAMP and updated_at_column is not None:
            return f"{prefix}{updated_at_column}"
        return current_timestamp

    @staticmethod
    def hard_delete_close_sql(
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        valid_to_column: str,
        current_timestamp: str,
    ) -> str:
        """Render the statement that closes active versions whose key is missing from the source."""

        missing_key_condition: str = SnapshotSql.key_condition(
            left_alias="__source", right_alias="__target", unique_key=unique_key
        )
        first_key: str = unique_key[0]
        return (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = {current_timestamp} "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND NOT EXISTS ("
            f"SELECT 1 FROM {origin} AS __source "
            f"WHERE {missing_key_condition} AND __source.{first_key} IS NOT NULL"
            f")"
        )
