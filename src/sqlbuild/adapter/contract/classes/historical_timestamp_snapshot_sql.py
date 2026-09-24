"""Shared SQL for historical timestamp snapshots."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.historical_snapshot_sql import HistoricalSnapshotSql
from sqlbuild.adapter.contract.classes.historical_snapshot_statement_sql import (
    HistoricalSnapshotStatementSql,
)
from sqlbuild.adapter.contract.classes.snapshot_sql import SnapshotSql
from sqlbuild.adapter.contract.models import SnapshotSqlDialect


class HistoricalTimestampSnapshotSql:
    """Render SQL for historical timestamp and historical changes snapshots."""

    def __init__(self, *, dialect: SnapshotSqlDialect) -> None:
        self.dialect: SnapshotSqlDialect = dialect

    def initial_select_sql(
        self,
        *,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> str:
        """Render the initial-build query for a historical timestamp snapshot."""

        if invalidate_hard_deletes:
            return HistoricalSnapshotSql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                updated_at_column=updated_at_column,
                distinct_condition=self.dialect.distinct_condition,
            ).initial_select_sql(output_columns=output_columns)

        partition_sql: str = ", ".join(unique_key)
        output_select_sql: str = ", ".join(output_columns)
        ordered_ctes_sql: str = self._ordered_ctes_sql(
            origin=origin,
            unique_key=unique_key,
            updated_at_column=updated_at_column,
            observed_at_column=observed_at_column,
            changes_cte="__changes",
        )
        return (
            f"WITH {ordered_ctes_sql} "
            f"SELECT {output_select_sql}, {updated_at_column} AS {valid_from_column}, "
            f"LEAD({updated_at_column}) OVER (PARTITION BY {partition_sql} "
            f"ORDER BY {updated_at_column}) AS {valid_to_column} "
            "FROM __changes"
        )

    def apply_sql(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        """Render the incremental statements for a historical timestamp snapshot."""

        statements: HistoricalSnapshotStatementSql = HistoricalSnapshotStatementSql(
            dialect=self.dialect
        )
        new_changes_sql: str
        if invalidate_hard_deletes:
            new_changes_sql = HistoricalSnapshotSql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                updated_at_column=updated_at_column,
                distinct_condition=self.dialect.distinct_condition,
            ).new_changes_ctes_sql(destination=destination)
        else:
            ordered_ctes_sql: str = self._ordered_ctes_sql(
                origin=origin,
                unique_key=unique_key,
                updated_at_column=updated_at_column,
                observed_at_column=observed_at_column,
                changes_cte="__delta_changes",
            )
            latest_sql: str = statements.latest_version_cte_sql(
                destination=destination, unique_key=unique_key, order_column=valid_from_column
            )
            latest_join_condition: str = SnapshotSql.key_condition(
                left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
            )
            new_changes_sql = (
                f"{ordered_ctes_sql}, {latest_sql}, __new_changes AS ("
                "SELECT __delta_changes.* FROM __delta_changes "
                f"LEFT JOIN __latest ON {latest_join_condition} "
                f"WHERE __latest.{unique_key[0]} IS NULL "
                f"OR __delta_changes.{updated_at_column} > __latest.{valid_from_column})"
            )
        return statements.apply_sql(
            destination=destination,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            change_time_column=updated_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )

    @staticmethod
    def changes_initial_select_sql(
        *,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> str:
        """Render the initial-build query for a historical changes snapshot."""

        partition_sql: str = ", ".join(unique_key)
        output_select_sql: str = ", ".join(output_columns)
        return (
            f"SELECT {output_select_sql}, {updated_at_column} AS {valid_from_column}, "
            f"LEAD({updated_at_column}) OVER (PARTITION BY {partition_sql} "
            f"ORDER BY {updated_at_column}) AS {valid_to_column} "
            f"FROM {origin}"
        )

    def changes_apply_sql(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Render the incremental statements for a historical changes snapshot."""

        statements: HistoricalSnapshotStatementSql = HistoricalSnapshotStatementSql(
            dialect=self.dialect
        )
        latest_sql: str = statements.latest_version_cte_sql(
            destination=destination, unique_key=unique_key, order_column=updated_at_column
        )
        latest_join_condition: str = SnapshotSql.key_condition(
            left_alias="__source", right_alias="__latest", unique_key=unique_key
        )
        new_changes_sql: str = (
            f"{latest_sql}, __new_changes AS ("
            f"SELECT __source.* FROM {origin} AS __source "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{unique_key[0]} IS NULL "
            f"OR __source.{updated_at_column} > __latest.{updated_at_column})"
        )
        return statements.apply_sql(
            destination=destination,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            change_time_column=updated_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=False,
        )

    def _ordered_ctes_sql(
        self,
        *,
        origin: str,
        unique_key: tuple[str, ...],
        updated_at_column: str,
        observed_at_column: str,
        changes_cte: str,
    ) -> str:
        partition_sql: str = ", ".join(unique_key)
        changed_sql: str = self.dialect.distinct_condition(
            left=updated_at_column, right="__prev_updated_at"
        )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({updated_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_updated_at FROM {origin}"
            f"), {changes_cte} AS ("
            f"SELECT * FROM __ordered WHERE __prev_updated_at IS NULL OR {changed_sql})"
        )
