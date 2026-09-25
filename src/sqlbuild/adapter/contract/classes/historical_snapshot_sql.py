"""Portable SQL for historical snapshots that invalidate hard deletes."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.constants import SNAPSHOT_VERSION_START_COLUMN


def render_is_distinct_from(*, left: str, right: str) -> str:
    """Render a null-safe inequality with the SQL standard predicate."""

    return f"{left} IS DISTINCT FROM {right}"


def historical_insert_validity_sql() -> str:
    """Render ``valid_from, valid_to`` expressions selected from ``__new_changes``."""

    version_end_sql: str = _version_end_sql(alias="__new_changes")
    return f"__new_changes.{SNAPSHOT_VERSION_START_COLUMN}, {version_end_sql}"


def _version_end_sql(*, alias: str | None) -> str:
    prefix: str = f"{alias}." if alias is not None else ""
    next_start: str = f"{prefix}__next_version_start"
    next_absence: str = f"{prefix}__next_absence_at"
    return (
        f"CASE WHEN {next_start} IS NULL THEN {next_absence} "
        f"WHEN {next_absence} IS NULL THEN {next_start} "
        f"WHEN {next_absence} < {next_start} THEN {next_absence} "
        f"ELSE {next_start} END"
    )


class HistoricalSnapshotSql:
    """Render hard-delete historical snapshot SQL without QUALIFY or correlated subqueries."""

    def __init__(
        self,
        *,
        origin: str,
        unique_key: tuple[str, ...],
        observed_at_column: str,
        valid_from_column: str,
        valid_to_column: str,
        check_columns: tuple[str, ...] = (),
        updated_at_column: str | None = None,
        distinct_condition: Callable[..., str] = render_is_distinct_from,
    ) -> None:
        self.origin: str = origin
        self.unique_key: tuple[str, ...] = unique_key
        self.observed_at_column: str = observed_at_column
        self.valid_from_column: str = valid_from_column
        self.valid_to_column: str = valid_to_column
        self.check_columns: tuple[str, ...] = check_columns
        self.updated_at_column: str | None = updated_at_column
        self.distinct_condition: Callable[..., str] = distinct_condition

    def initial_select_sql(self, *, output_columns: tuple[str, ...]) -> str:
        """Render the complete initial-build query."""

        return (
            f"WITH {self.initial_ctes_sql()} "
            f"SELECT {self.initial_select_list_sql(output_columns=output_columns)} "
            "FROM __versions"
        )

    def initial_ctes_sql(self) -> str:
        """Render the initial-build CTE list ending in ``__versions``."""

        partition_sql: str = self._key_sql(alias=None)
        return (
            f"{self._tracked_source_ctes_sql()}, __changes AS ("
            f"SELECT *, {self._initial_version_start_sql()} AS {SNAPSHOT_VERSION_START_COLUMN} "
            "FROM __tracked "
            f"WHERE __is_change = 1 OR {self._initial_reappearance_sql()}"
            "), __versions AS ("
            f"SELECT *, LEAD({SNAPSHOT_VERSION_START_COLUMN}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {SNAPSHOT_VERSION_START_COLUMN}"
            ") AS __next_version_start FROM __changes"
            ")"
        )

    def initial_select_list_sql(self, *, output_columns: tuple[str, ...]) -> str:
        """Render output columns and validity columns selected from ``__versions``."""

        output_sql: str = ", ".join(output_columns)
        return (
            f"{output_sql}, {SNAPSHOT_VERSION_START_COLUMN} AS {self.valid_from_column}, "
            f"{_version_end_sql(alias=None)} AS {self.valid_to_column}"
        )

    def new_changes_ctes_sql(self, *, destination: str) -> str:
        """Render the incremental CTE list defining ``__new_changes`` and ``__hard_deletes``."""

        partition_sql: str = self._key_sql(alias=None)
        first_key: str = self.unique_key[0]
        latest_join_condition: str = self._key_condition(left="__tracked", right="__latest")
        return (
            f"{self._tracked_source_ctes_sql()}, __latest AS ("
            "SELECT * FROM ("
            f"SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition_sql} "
            f"ORDER BY {self.valid_from_column} DESC) AS __latest_rn FROM {destination}"
            ") AS __latest_ranked WHERE __latest_rn = 1"
            "), __classified AS ("
            "SELECT __tracked.*, "
            f"CASE WHEN __latest.{first_key} IS NULL THEN 0 ELSE 1 END AS __has_latest, "
            f"__latest.{self.valid_from_column} AS __latest_valid_from, "
            f"{self._differs_from_latest_sql()} AS __differs_from_latest, "
            f"{self._incremental_reappearance_sql()} AS __is_reappearance, "
            f"{self._unchanged_from_previous_sql()} AS __is_unchanged "
            f"FROM __tracked LEFT JOIN __latest ON {latest_join_condition}"
            "), __changed_or_new AS ("
            f"SELECT __classified.*, {self._incremental_version_start_sql()} "
            f"AS {SNAPSHOT_VERSION_START_COLUMN} FROM __classified "
            f"WHERE {self._incremental_start_condition_sql()}"
            f"), {self._new_change_starts_sql()}, __new_changes AS ("
            f"SELECT *, LEAD({SNAPSHOT_VERSION_START_COLUMN}) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {SNAPSHOT_VERSION_START_COLUMN}"
            ") AS __next_version_start FROM __new_change_starts"
            f"), __hard_deletes AS ({self._open_version_hard_deletes_sql(destination=destination)})"
        )

    def _tracked_source_ctes_sql(self) -> str:
        observed_at: str = self.observed_at_column
        partition_sql: str = self._key_sql(alias=None)
        window_sql: str = f"OVER (PARTITION BY {partition_sql} ORDER BY {observed_at})"
        return (
            "__observed_group_sequence AS ("
            "SELECT __observed_at, "
            "LAG(__observed_at) OVER (ORDER BY __observed_at) AS __prev_group_observed_at, "
            "LEAD(__observed_at) OVER (ORDER BY __observed_at) AS __next_group_observed_at "
            f"FROM (SELECT DISTINCT {observed_at} AS __observed_at FROM {self.origin}) "
            "AS __observed_group_values"
            "), __ordered AS ("
            "SELECT __source.*, __observed_group_sequence.__prev_group_observed_at, "
            "__observed_group_sequence.__next_group_observed_at, "
            f"LAG({observed_at}) {window_sql} AS __prev_observed_at, "
            f"LEAD({observed_at}) {window_sql} AS __next_observed_at"
            f"{self._previous_values_sql(window_sql=window_sql)} "
            f"FROM {self.origin} AS __source LEFT JOIN __observed_group_sequence "
            f"ON __observed_group_sequence.__observed_at = __source.{observed_at}"
            "), __flagged AS ("
            "SELECT *, "
            "CASE WHEN __next_group_observed_at IS NOT NULL AND (__next_observed_at IS NULL "
            "OR __next_observed_at <> __next_group_observed_at) "
            "THEN __next_group_observed_at END AS __absent_after, "
            f"CASE WHEN {self._change_condition_sql()} THEN 1 ELSE 0 END AS __is_change "
            "FROM __ordered"
            "), __tracked AS ("
            "SELECT *, MIN(__absent_after) OVER ("
            f"PARTITION BY {partition_sql} ORDER BY {observed_at} "
            "ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING"
            ") AS __next_absence_at FROM __flagged"
            ")"
        )

    def _previous_values_sql(self, *, window_sql: str) -> str:
        if self.updated_at_column is not None:
            return f", LAG({self.updated_at_column}) {window_sql} AS __prev_updated_at"
        return "".join(
            f", LAG({column}) {window_sql} AS __prev_{column}" for column in self.check_columns
        )

    def _change_condition_sql(self) -> str:
        if self.updated_at_column is not None:
            return "__prev_updated_at IS NULL OR " + self.distinct_condition(
                left=self.updated_at_column, right="__prev_updated_at"
            )
        changed_sql: str = " OR ".join(
            self.distinct_condition(left=column, right=f"__prev_{column}")
            for column in self.check_columns
        )
        return f"__prev_observed_at IS NULL OR ({changed_sql})"

    def _initial_reappearance_sql(self) -> str:
        return "(__prev_observed_at IS NOT NULL AND __prev_observed_at <> __prev_group_observed_at)"

    def _initial_version_start_sql(self) -> str:
        return self._version_start_sql(
            unchanged_reappearance_sql=f"{self._initial_reappearance_sql()} AND __is_change = 0"
        )

    def _incremental_reappearance_sql(self) -> str:
        return (
            "CASE WHEN __tracked.__prev_group_observed_at IS NOT NULL AND ("
            f"(__tracked.__prev_observed_at IS NULL AND __latest.{self.unique_key[0]} IS NOT NULL) "
            "OR __tracked.__prev_observed_at <> __tracked.__prev_group_observed_at"
            ") THEN 1 ELSE 0 END"
        )

    def _incremental_version_start_sql(self) -> str:
        return self._version_start_sql(
            unchanged_reappearance_sql="__is_reappearance = 1 AND __is_unchanged = 1"
        )

    def _version_start_sql(self, *, unchanged_reappearance_sql: str) -> str:
        if self.updated_at_column is None:
            return self.observed_at_column
        return (
            f"CASE WHEN {unchanged_reappearance_sql} THEN {self.observed_at_column} "
            f"ELSE {self.updated_at_column} END"
        )

    def _unchanged_from_previous_sql(self) -> str:
        if self.updated_at_column is None:
            return "0"
        changed_from_latest_sql: str = self.distinct_condition(
            left=f"__tracked.{self.updated_at_column}",
            right=f"__latest.{self.updated_at_column}",
        )
        return (
            "CASE WHEN __tracked.__prev_observed_at IS NOT NULL AND __tracked.__is_change = 0 "
            "THEN 1 "
            "WHEN __tracked.__prev_observed_at IS NULL AND __latest."
            f"{self.unique_key[0]} IS NOT NULL AND NOT ({changed_from_latest_sql}) THEN 1 "
            "ELSE 0 END"
        )

    def _differs_from_latest_sql(self) -> str:
        if not self.check_columns:
            return "0"
        differs_sql: str = " OR ".join(
            self.distinct_condition(left=f"__tracked.{column}", right=f"__latest.{column}")
            for column in self.check_columns
        )
        return f"CASE WHEN {differs_sql} THEN 1 ELSE 0 END"

    def _incremental_start_condition_sql(self) -> str:
        return (
            "(__has_latest = 0 AND (__is_change = 1 OR __is_reappearance = 1)) "
            "OR (__has_latest = 1 AND __is_reappearance = 1 "
            f"AND {self._incremental_version_start_sql()} > __latest_valid_from) "
            "OR (__has_latest = 1 AND __is_reappearance = 0 AND __is_change = 1 "
            f"AND {self._latest_change_condition_sql()})"
        )

    def _latest_change_condition_sql(self) -> str:
        if self.updated_at_column is not None:
            return f"{self.updated_at_column} > __latest_valid_from"
        return (
            f"{self.observed_at_column} > __latest_valid_from "
            "AND (__prev_observed_at >= __latest_valid_from OR __differs_from_latest = 1)"
        )

    def _new_change_starts_sql(self) -> str:
        observed_at: str = self.observed_at_column
        classified_key_sql: str = self._key_sql(alias="__classified")
        return (
            "__first_new_starts AS ("
            f"SELECT {self._key_sql(alias=None)}, MIN({SNAPSHOT_VERSION_START_COLUMN}) "
            f"AS __first_version_start FROM __changed_or_new GROUP BY {self._key_sql(alias=None)}"
            "), __reappearances AS ("
            f"SELECT {classified_key_sql}, MIN(__classified.{observed_at}) AS __reappeared_at "
            "FROM __classified "
            f"JOIN __latest ON {self._key_condition(left='__classified', right='__latest')} "
            "LEFT JOIN __observed_group_sequence AS __closing_group "
            f"ON __closing_group.__observed_at = __latest.{self.valid_to_column} "
            f"WHERE __latest.{self.valid_to_column} IS NOT NULL "
            "AND __closing_group.__observed_at IS NULL "
            f"AND __classified.{observed_at} > __latest.{self.valid_to_column} "
            f"GROUP BY {classified_key_sql}"
            "), __new_change_starts AS ("
            "SELECT * FROM __changed_or_new "
            "UNION ALL "
            f"SELECT __classified.*, __classified.{observed_at} AS {SNAPSHOT_VERSION_START_COLUMN} "
            "FROM __classified "
            "JOIN __reappearances ON "
            f"{self._key_condition(left='__classified', right='__reappearances')} "
            f"AND __classified.{observed_at} = __reappearances.__reappeared_at "
            "LEFT JOIN __first_new_starts ON "
            f"{self._key_condition(left='__classified', right='__first_new_starts')} "
            f"WHERE __first_new_starts.{self.unique_key[0]} IS NULL "
            f"OR __classified.{observed_at} < __first_new_starts.__first_version_start"
            ")"
        )

    def _open_version_hard_deletes_sql(self, *, destination: str) -> str:
        target_key_sql: str = self._key_sql(alias="__target")
        present_condition: str = self._key_condition(left="__present", right="__target")
        observed_at: str = self.observed_at_column
        return (
            f"SELECT {target_key_sql}, MIN(__observed_groups.__observed_at) AS __close_at "
            f"FROM {destination} AS __target "
            "JOIN __observed_group_sequence AS __observed_groups "
            f"ON __observed_groups.__observed_at > __target.{observed_at} "
            f"LEFT JOIN {self.origin} AS __present "
            f"ON __present.{observed_at} = __observed_groups.__observed_at "
            f"AND {present_condition} "
            f"WHERE __target.{self.valid_to_column} IS NULL "
            f"AND __present.{self.unique_key[0]} IS NULL "
            f"GROUP BY {target_key_sql}"
        )

    def _key_sql(self, *, alias: str | None) -> str:
        prefix: str = f"{alias}." if alias is not None else ""
        return ", ".join(f"{prefix}{column}" for column in self.unique_key)

    def _key_condition(self, *, left: str, right: str) -> str:
        return " AND ".join(f"{left}.{column} = {right}.{column}" for column in self.unique_key)
