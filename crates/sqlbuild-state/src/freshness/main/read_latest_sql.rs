//! `read_latest_sql`: the windowed SELECT of the latest state row per source identity.

use crate::freshness::constants::SOURCE_FRESHNESS_COLUMN_TYPES;

/// Latest row per source, target database, schema and name, newest observation and run first.
pub fn read_latest_sql(qualified_name: &str) -> String {
    let columns: String = SOURCE_FRESHNESS_COLUMN_TYPES
        .iter()
        .map(|(column, _)| *column)
        .collect::<Vec<_>>()
        .join(", ");
    format!(
        "SELECT {columns} FROM (SELECT {columns}, ROW_NUMBER() OVER (\
PARTITION BY source_name, target_database, target_schema, target_name \
ORDER BY observed_at DESC, run_id DESC) AS __sqlbuild_latest_rank FROM {qualified_name}) \
AS __sqlbuild_latest_source_freshness WHERE __sqlbuild_latest_rank = 1"
    )
}
