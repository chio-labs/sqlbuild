//! A row's key values joined as conflicts record them.

use crate::clickhouse::_helpers::literals::{column_type, key_text};
use crate::records::models::RecallRow;
use crate::schema::main::table_spec::table_spec;

/// The key of `row`, its values joined by `:`.
pub(crate) fn record_key(row: &RecallRow) -> String {
    let mut parts: Vec<String> = Vec::new();
    for name in table_spec(row.table).key {
        parts.push(key_text(row.value(name), column_type(row.table, name)));
    }
    parts.join(":")
}
