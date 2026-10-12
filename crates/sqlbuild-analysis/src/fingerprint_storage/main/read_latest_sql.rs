//! The latest-row read of the fingerprint table.

use crate::fingerprint_storage::_helpers::table_columns::column_list;
use crate::fingerprint_storage::constants::{
    COLUMN_NODE_NAME, COLUMN_NODE_TYPE, COLUMN_RUN_ID, COLUMN_TIMESTAMP,
};

/// A windowed `SELECT` of the latest row per node identity.
pub fn read_latest_sql(qualified_name: &str) -> String {
    let columns: String = column_list();
    format!(
        "SELECT {columns} FROM (SELECT {columns}, ROW_NUMBER() OVER (\
         PARTITION BY {COLUMN_NODE_TYPE}, {COLUMN_NODE_NAME} \
         ORDER BY {COLUMN_TIMESTAMP} DESC, {COLUMN_RUN_ID} DESC) AS __sqlbuild_latest_rank \
         FROM {qualified_name}) AS __sqlbuild_latest_fingerprints \
         WHERE __sqlbuild_latest_rank = 1"
    )
}
