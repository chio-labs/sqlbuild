"""Shared SQL for historical check snapshots."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.historical_snapshot_sql import HistoricalSnapshotSql
from sqlbuild.adapter.contract.classes.snapshot_sql import SnapshotSql


class HistoricalCheckSnapshotSql:
    """Render SQL for historical check snapshots."""

    @staticmethod
    def initial_select_sql(
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
            ).initial_select_sql(output_columns=output_columns)

        partition_sql: str = ", ".join(unique_key)
        previous_columns_sql: str = ", ".join(
            f"LAG({column}) OVER (PARTITION BY {partition_sql} ORDER BY {observed_at_column}) "
            f"AS __prev_{column}"
            for column in check_columns
        )
        if previous_columns_sql:
            previous_columns_sql = f", {previous_columns_sql}"
        change_condition: str = " OR ".join(
            f"{column} IS DISTINCT FROM __prev_{column}" for column in check_columns
        )
        output_select_sql: str = ", ".join(column for column in output_columns)
        return (
            "WITH __ordered AS ("
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
            "), __changes AS ("
            f"SELECT * FROM __ordered WHERE __prev_observed_at IS NULL OR ({change_condition})"
            ") "
            f"SELECT {output_select_sql}, {observed_at_column} AS {valid_from_column}, "
            f"LEAD({observed_at_column}) OVER (PARTITION BY {partition_sql} "
            f"ORDER BY {observed_at_column}) AS {valid_to_column} "
            "FROM __changes"
        )

    @staticmethod
    def new_changes_ctes_sql(
        *,
        destination: str,
        origin: str,
        unique_key: tuple[str, ...],
        check_columns: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        invalidate_hard_deletes: bool,
    ) -> str:
        """Render incremental historical check CTEs using ``QUALIFY`` for the latest versions."""

        if invalidate_hard_deletes:
            return HistoricalSnapshotSql(
                origin=origin,
                unique_key=unique_key,
                observed_at_column=observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                check_columns=check_columns,
            ).new_changes_ctes_sql(destination=destination)

        partition_sql: str = ", ".join(unique_key)
        previous_columns_sql: str = ", ".join(
            f"LAG({column}) OVER (PARTITION BY {partition_sql} ORDER BY {observed_at_column}) "
            f"AS __prev_{column}"
            for column in check_columns
        )
        if previous_columns_sql:
            previous_columns_sql = f", {previous_columns_sql}"
        delta_change_condition: str = " OR ".join(
            f"{column} IS DISTINCT FROM __prev_{column}" for column in check_columns
        )
        latest_join_condition: str = SnapshotSql.key_condition(
            left_alias="__delta_changes", right_alias="__latest", unique_key=unique_key
        )
        latest_change_condition: str = " OR ".join(
            f"__delta_changes.{column} IS DISTINCT FROM __latest.{column}"
            for column in check_columns
        )
        first_key: str = unique_key[0]
        changed_or_first_sql: str = (
            "SELECT * FROM __ordered WHERE __prev_observed_at IS NULL "
            f"OR ({delta_change_condition})"
        )
        return (
            "__ordered AS ("
            f"SELECT *, LAG({observed_at_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at_column}"
            f") AS __prev_observed_at{previous_columns_sql} FROM {origin}"
            "), __delta_changes AS ("
            f"{changed_or_first_sql}"
            "), __latest AS ("
            f"SELECT * FROM {destination} QUALIFY ROW_NUMBER() OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {valid_from_column} DESC"
            ") = 1"
            "), __new_changes AS ("
            "SELECT __delta_changes.* FROM __delta_changes "
            f"LEFT JOIN __latest ON {latest_join_condition} "
            f"WHERE __latest.{first_key} IS NULL OR ("
            f"__delta_changes.{observed_at_column} > __latest.{valid_from_column} "
            f"AND ({latest_change_condition})"
            ")"
            ")"
        )
