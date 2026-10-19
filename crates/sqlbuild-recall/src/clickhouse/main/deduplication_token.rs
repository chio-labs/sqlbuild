//! `deduplication_token`: the `insert_deduplication_token` of one table's insert block.

use crate::clickhouse::_helpers::record_key::record_key;
use crate::records::main::sha256_hex::sha256_hex;
use crate::records::models::RecallRow;
use crate::schema::main::table_spec::table_spec;

/// A digest of the table and each row's key and content, so a retried block is recognised.
#[must_use]
pub fn deduplication_token(rows: &[RecallRow]) -> String {
    let mut material: String = String::new();
    if let Some(first) = rows.first() {
        material.push_str(table_spec(first.table).name);
    }
    for row in rows {
        material.push('\n');
        material.push_str(&record_key(row));
        material.push('\u{0}');
        material.push_str(row.content_hash().unwrap_or_default());
    }
    sha256_hex(material.as_bytes())
}
