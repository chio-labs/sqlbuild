"""Shared SQL for historical check snapshots."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.historical_snapshot_sql import HistoricalSnapshotSql
from sqlbuild.adapter.contract.classes.historical_snapshot_statement_sql import (
    HistoricalSnapshotStatementSql,
)
from sqlbuild.adapter.contract.classes.snapshot_sql import SnapshotSql
from sqlbuild.adapter.contract.models import SnapshotSqlDialect


class HistoricalCheckSnapshotSql:
    """Render SQL for historical check snapshots."""

    def __init__(self, *, dialect: SnapshotSqlDialect) -> None:
        self.dialect: SnapshotSqlDialect = dialect

    def initial_select_sql(
        self,
        *,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> str:
        """Render the initial-build query for a historical check snapshot."""

        if invalidate_hard_deletes:
            return HistoricalSnapshotSql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                check_columns=check_columns,
                distinct_condition=self.dialect.distinct_condition,
            ).initial_select_sql(output_columns=output_columns)

        partition_sql: str = ", ".join(unique_key)
        change_condition: str = " OR ".join(
            self.dialect.distinct_condition(left=column, right=f"__prev_{column}")
            for column in check_columns
        )
        output_select_sql: str = ", ".join(output_columns)
        ordered_sql: str = self._ordered_select_sql(
            origin=origin,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
        )
        return (
            f"WITH __ordered AS ({ordered_sql}), __changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_observed_at IS NULL OR ({change_condition})"
            ") "
            f"SELECT {output_select_sql}, {observed_at_column} AS {valid_from_column}, "
            f"LEAD({observed_at_column}) OVER (PARTITION BY {partition_sql} "
            f"ORDER BY {observed_at_column}) AS {valid_to_column} "
            "FROM __changes"
        )

    def apply_sql(
        self,
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        """Render the incremental statements for a historical check snapshot."""

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
                check_columns=check_columns,
                distinct_condition=self.dialect.distinct_condition,
            ).new_changes_ctes_sql(destination=destination)
        else:
            new_changes_sql = self._new_changes_ctes_sql(
                statements=statements,
                destination=destination,
                origin=origin,
                unique_key=unique_key,
                check_columns=check_columns,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
            )
        return statements.apply_sql(
            destination=destination,
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            change_time_column=observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=invalidate_hard_deletes,
        )

    def _new_changes_ctes_sql(
        self,
        *,
        statements: HistoricalSnapshotStatementSql,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
    ) -> str:
        delta_change_condition: str = " OR ".join(
            self.dialect.distinct_condition(left=column, right=f"__prev_{column}")
            for column in check_columns
        )
        latest_join_condition: str = SnapshotSql.key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        latest_change_condition: str = " OR ".join(
            self.dialect.distinct_condition(
                left=f"__delta_changes.{column}", right=f"__latest.{column}"
            )
            for column in check_columns
        )
        latest_sql: str = statements.latest_version_cte_sql(
            destination=destination, unique_key=unique_key, order_column=valid_from_column
        )
        ordered_sql: str = self._ordered_select_sql(
            origin=origin,
            unique_key=unique_key,
            check_columns=check_columns,
            observed_at_column=observed_at_column,
        )
        return (
            f"__ordered AS ({ordered_sql}), __delta_changes AS ("
            "SELECT * FROM __ordered WHERE __prev_observed_at IS NULL "
            f"OR ({delta_change_condition})"
            f"), {latest_sql}, __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{unique_key[0]} IS NULL OR ("
            f"__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
            f"AND ({latest_change_condition})))"
        )

    @staticmethod
    def _ordered_select_sql(
        *,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
    ) -> str:
        partition_sql: str = ", ".join(unique_key)
        previous_columns_sql: str = "".join(
            f", LAG({column}) OVER (PARTITION BY {partition_sql} ORDER BY {observed_at_column}) "
            f"AS __prev_{column}"
            for column in check_columns
        )
        return (
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
        )
