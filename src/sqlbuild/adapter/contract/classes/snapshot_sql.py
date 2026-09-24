"""Shared SQL fragments for snapshot materializations."""

from __future__ import annotations


class SnapshotSql:
    """Render SQL fragments shared by snapshot materializations."""

    @staticmethod
    def key_condition(*, left_alias: str, right_alias: str, unique_key: tuple[str, ...]) -> str:
        """Render the equality join between two aliases over the snapshot unique key."""

        return " AND ".join(
            f"{left_alias}.{column} = {right_alias}.{column}" for column in unique_key
        )
