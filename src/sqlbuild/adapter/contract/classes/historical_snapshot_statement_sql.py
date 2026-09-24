"""Shared close and insert statements for historical snapshots."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.snapshot_sql import SnapshotSql


class HistoricalSnapshotStatementSql:
    """Render close and insert statements shared by historical snapshots."""

    @staticmethod
    def grouped_combined_close_sql(
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        change_time_column: str,
    ) -> str:
        """Render an ``UPDATE ... FROM`` close over new versions and hard deletes."""

        candidate_key_sql: str = ", ".join(unique_key)
        return HistoricalSnapshotStatementSql.grouped_close_sql(
            destination=destination,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            close_candidates_sql=(
                f"SELECT {candidate_key_sql}, {change_time_column} AS __close_at "
                "FROM __new_changes "
                "UNION ALL "
                f"SELECT {candidate_key_sql}, __close_at FROM __hard_deletes "
                "WHERE __close_at IS NOT NULL"
            ),
        )

    @staticmethod
    def grouped_close_sql(
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        close_candidates_sql: str,
    ) -> str:
        """Render an ``UPDATE ... FROM`` close that uses the earliest candidate per key."""

        close_candidate_condition: str = SnapshotSql.key_condition(
            left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
        )
        candidate_key_sql: str = ", ".join(unique_key)
        close_candidates_query: str = (
            f"WITH {new_changes_sql}, __close_candidates AS ({close_candidates_sql}) "
            f"SELECT {candidate_key_sql}, MIN(__close_at) AS __close_at "
            "FROM __close_candidates GROUP BY "
            f"{candidate_key_sql}"
        )
        return (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = __close_candidates.__close_at "
            f"FROM ({close_candidates_query}) AS __close_candidates "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < __close_candidates.__close_at "
            f"AND {close_candidate_condition}"
        )

    @staticmethod
    def insert_with_cte_sql(
        *, destination: str, insert_column_sql: str, new_changes_sql: str, select_sql: str
    ) -> str:
        """Render an insert whose CTEs follow the ``INSERT INTO`` column list."""

        return (
            f"INSERT INTO {destination} ({insert_column_sql}) WITH {new_changes_sql} {select_sql}"
        )
