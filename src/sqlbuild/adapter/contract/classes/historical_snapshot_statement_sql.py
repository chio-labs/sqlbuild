"""Shared close and insert statements for historical snapshots."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.historical_snapshot_sql import (
    historical_insert_validity_sql,
)
from sqlbuild.adapter.contract.classes.snapshot_sql import SnapshotSql
from sqlbuild.adapter.contract.constants import SNAPSHOT_VERSION_START_COLUMN
from sqlbuild.adapter.contract.models import SnapshotSqlDialect
from sqlbuild.adapter.contract.types import (
    HistoricalSnapshotCloseStyle,
    HistoricalSnapshotInsertStyle,
    SnapshotLatestVersionStyle,
)


class HistoricalSnapshotStatementSql:
    """Render latest-version, close and insert statements shared by historical snapshots."""

    def __init__(self, *, dialect: SnapshotSqlDialect) -> None:
        self.dialect: SnapshotSqlDialect = dialect

    def latest_version_cte_sql(
        self, *, destination: str, unique_key: tuple[str, ...], order_column: str
    ) -> str:
        """Render CTEs ending in ``__latest``, the newest stored version of each key."""

        partition_sql: str = ", ".join(unique_key)
        window_sql: str = (
            f"ROW_NUMBER() OVER (PARTITION BY {partition_sql} ORDER BY {order_column} DESC)"
        )
        if self.dialect.latest_version == SnapshotLatestVersionStyle.QUALIFY:
            return f"__latest AS (SELECT * FROM {destination} QUALIFY {window_sql} = 1)"
        if self.dialect.latest_version == SnapshotLatestVersionStyle.DERIVED_TABLE:
            return (
                f"__latest AS (SELECT * FROM (SELECT *, {window_sql} AS __rn FROM {destination}) "
                "AS __q WHERE __rn = 1)"
            )
        return (
            f"__latest_ordered AS (SELECT *, {window_sql} AS __rn FROM {destination}), "
            "__latest AS (SELECT * FROM __latest_ordered WHERE __rn = 1)"
        )

    def apply_sql(
        self,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        change_time_column: str,
        valid_from_column: str,
        valid_to_column: str,
        output_columns: tuple[str, ...],
        invalidate_hard_deletes: bool,
    ) -> tuple[str, ...]:
        """Render the close and insert statements that apply ``__new_changes``."""

        close_sql: str
        if invalidate_hard_deletes:
            close_sql = self._combined_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=SNAPSHOT_VERSION_START_COLUMN,
            )
        else:
            close_sql = self._change_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                change_time_column=change_time_column,
            )
        insert_column_sql: str = ", ".join((*output_columns, valid_from_column, valid_to_column))
        output_select_sql: str = ", ".join(f"__new_changes.{column}" for column in output_columns)
        partition_sql: str = ", ".join(f"__new_changes.{column}" for column in unique_key)
        version_columns_sql: str = (
            f"__new_changes.{change_time_column}, LEAD(__new_changes.{change_time_column}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY __new_changes.{change_time_column})"
        )
        if invalidate_hard_deletes:
            version_columns_sql = historical_insert_validity_sql()
        insert_sql: str = self._insert_sql(
            destination=destination,
            insert_column_sql=insert_column_sql,
            new_changes_sql=new_changes_sql,
            select_sql=f"SELECT {output_select_sql}, {version_columns_sql} FROM __new_changes",
        )
        return (close_sql, insert_sql)

    def _change_close_sql(
        self,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        change_time_column: str,
    ) -> str:
        if self.dialect.historical_close == HistoricalSnapshotCloseStyle.UPDATE_FROM:
            return self._grouped_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                close_candidates_sql=(
                    f"SELECT {', '.join(unique_key)}, {change_time_column} AS __close_at "
                    "FROM __new_changes"
                ),
            )
        key_condition: str = SnapshotSql.key_condition(
            left_alias="__target", right_alias="__new_changes", unique_key=unique_key
        )
        return self._correlated_close_sql(
            ctes_sql=new_changes_sql,
            destination=destination,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            close_at_sql=(
                f"SELECT MIN(__new_changes.{change_time_column}) "
                f"FROM __new_changes WHERE {key_condition}"
            ),
            exists_sql=f"SELECT 1 FROM __new_changes WHERE {key_condition}",
        )

    def _combined_close_sql(
        self,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        change_time_column: str,
    ) -> str:
        candidate_key_sql: str = ", ".join(unique_key)
        close_candidates_sql: str = (
            f"SELECT {candidate_key_sql}, {change_time_column} AS __close_at FROM __new_changes "
            "UNION ALL "
            f"SELECT {candidate_key_sql}, __close_at FROM __hard_deletes "
            "WHERE __close_at IS NOT NULL"
        )
        if self.dialect.historical_close == HistoricalSnapshotCloseStyle.UPDATE_FROM:
            return self._grouped_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                close_candidates_sql=close_candidates_sql,
            )
        if self.dialect.historical_close == HistoricalSnapshotCloseStyle.MERGE_HARD_DELETES:
            return self._merge_close_sql(
                destination=destination,
                new_changes_sql=new_changes_sql,
                unique_key=unique_key,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                close_candidates_sql=close_candidates_sql,
            )
        close_candidate_condition: str = SnapshotSql.key_condition(
            left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
        )
        return self._correlated_close_sql(
            ctes_sql=f"{new_changes_sql}, __close_candidates AS ({close_candidates_sql})",
            destination=destination,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            close_at_sql=(
                "SELECT MIN(__close_candidates.__close_at) FROM __close_candidates "
                f"WHERE {close_candidate_condition}"
            ),
            exists_sql=f"SELECT 1 FROM __close_candidates WHERE {close_candidate_condition}",
        )

    def _correlated_close_sql(
        self,
        *,
        ctes_sql: str,
        destination: str,
        valid_from_column: str,
        valid_to_column: str,
        close_at_sql: str,
        exists_sql: str,
    ) -> str:
        update_sql: str = (
            f"WITH {ctes_sql} UPDATE {destination} AS __target "
            f"SET {valid_to_column} = ({close_at_sql}) "
        )
        if self.dialect.historical_close == HistoricalSnapshotCloseStyle.TSQL:
            update_sql = (
                f";WITH {ctes_sql} UPDATE __target SET {valid_to_column} = ({close_at_sql}) "
                f"FROM {destination} AS __target "
            )
        return (
            f"{update_sql}WHERE __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < ({close_at_sql}) "
            f"AND EXISTS ({exists_sql})"
        )

    def _grouped_close_sql(
        self,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        close_candidates_sql: str,
    ) -> str:
        close_candidate_condition: str = SnapshotSql.key_condition(
            left_alias="__close_candidates", right_alias="__target", unique_key=unique_key
        )
        close_candidates_query: str = self._earliest_close_candidates_sql(
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            close_candidates_sql=close_candidates_sql,
        )
        return (
            f"UPDATE {destination} AS __target "
            f"SET {valid_to_column} = __close_candidates.__close_at "
            f"FROM ({close_candidates_query}) AS __close_candidates "
            f"WHERE __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < __close_candidates.__close_at "
            f"AND {close_candidate_condition}"
        )

    def _merge_close_sql(
        self,
        *,
        destination: str,
        new_changes_sql: str,
        unique_key: tuple[str, ...],
        valid_from_column: str,
        valid_to_column: str,
        close_candidates_sql: str,
    ) -> str:
        close_candidate_condition: str = SnapshotSql.key_condition(
            left_alias="__target", right_alias="__close_candidates", unique_key=unique_key
        )
        close_candidates_query: str = self._earliest_close_candidates_sql(
            new_changes_sql=new_changes_sql,
            unique_key=unique_key,
            close_candidates_sql=close_candidates_sql,
        )
        return (
            f"MERGE INTO {destination} AS __target "
            f"USING ({close_candidates_query}) AS __close_candidates "
            f"ON {close_candidate_condition} "
            f"AND __target.{valid_to_column} IS NULL "
            f"AND __target.{valid_from_column} < __close_candidates.__close_at "
            f"WHEN MATCHED THEN UPDATE SET {valid_to_column} = __close_candidates.__close_at"
        )

    @staticmethod
    def _earliest_close_candidates_sql(
        *, new_changes_sql: str, unique_key: tuple[str, ...], close_candidates_sql: str
    ) -> str:
        candidate_key_sql: str = ", ".join(unique_key)
        return (
            f"WITH {new_changes_sql}, __close_candidates AS ({close_candidates_sql}) "
            f"SELECT {candidate_key_sql}, MIN(__close_at) AS __close_at "
            f"FROM __close_candidates GROUP BY {candidate_key_sql}"
        )

    def _insert_sql(
        self, *, destination: str, insert_column_sql: str, new_changes_sql: str, select_sql: str
    ) -> str:
        insert_sql: str = f"INSERT INTO {destination} ({insert_column_sql})"
        if self.dialect.historical_insert == HistoricalSnapshotInsertStyle.INSERT_WITH:
            return f"{insert_sql} WITH {new_changes_sql} {select_sql}"
        if self.dialect.historical_insert == HistoricalSnapshotInsertStyle.TSQL:
            return f";WITH {new_changes_sql} {insert_sql} {select_sql}"
        return f"WITH {new_changes_sql} {insert_sql} {select_sql}"
