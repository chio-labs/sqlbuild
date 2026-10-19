//! `stored_rows_sql`: what the keys of one batch already hold in a ClickHouse store.

use std::collections::BTreeMap;

use crate::clickhouse::_helpers::literals::{
    column_type, key_text_expression, string_literal, value_literal,
};
use crate::clickhouse::constants::{TIMESTAMP_PATTERN, UNCHECKED_TABLES};
use crate::records::models::RecallRow;
use crate::schema::main::clickhouse_relation::clickhouse_relation;
use crate::schema::main::table_spec::table_spec;
use crate::schema::models::{DdlOptions, Table};

fn distinct_literals(table: Table, rows: &[&RecallRow], column: &str) -> String {
    let mut literals: Vec<String> = rows
        .iter()
        .filter_map(|row| row.value(column))
        .map(|value| value_literal(value, column_type(table, column)))
        .collect();
    literals.sort();
    literals.dedup();
    literals.join(", ")
}

fn table_lookup(table: Table, rows: &[&RecallRow], options: &DdlOptions) -> String {
    let spec = table_spec(table);
    let key: Vec<String> = spec
        .key
        .iter()
        .map(|column| key_text_expression(table, column))
        .collect();
    let mut filters: Vec<String> = Vec::new();
    if !spec.key.contains(&"invocation_id") && table != Table::Artifacts {
        filters.push(format!(
            "invocation_id IN ({})",
            distinct_literals(table, rows, "invocation_id")
        ));
    }
    for column in spec.key {
        filters.push(format!(
            "`{column}` IN ({})",
            distinct_literals(table, rows, column)
        ));
    }
    let newest: String = if table == Table::Artifacts {
        format!("formatDateTime(max(seen_at), '{TIMESTAMP_PATTERN}', 'UTC')")
    } else {
        "''".to_owned()
    };
    format!(
        "SELECT {dataset} AS dataset, {key} AS record_key, \
         argMin(content_hash, ingested_at) AS first_hash, \
         arrayStringConcat(groupUniqArray(content_hash), ',') AS hashes, {newest} AS newest_seen_at \
         FROM {name} WHERE {filters} GROUP BY record_key",
        dataset = string_literal(spec.name),
        key = if key.len() == 1 {
            key[0].clone()
        } else {
            format!("concat({})", key.join(", ':', "))
        },
        name = clickhouse_relation(spec.name, options),
        filters = filters.join(" AND "),
    )
}

/// One `UNION ALL` query over every checked table of `rows`, `None` when no row needs a lookup. Columns: `dataset`, `record_key`, `first_hash`, `hashes`, `newest_seen_at` (artifacts only, else empty).
#[must_use]
pub fn stored_rows_sql(rows: &[RecallRow], options: &DdlOptions) -> Option<String> {
    let mut by_table: BTreeMap<Table, Vec<&RecallRow>> = BTreeMap::new();
    for row in rows {
        if !UNCHECKED_TABLES.contains(&row.table) {
            by_table.entry(row.table).or_default().push(row);
        }
    }
    if by_table.is_empty() {
        return None;
    }
    Some(
        by_table
            .iter()
            .map(|(table, rows)| table_lookup(*table, rows, options))
            .collect::<Vec<_>>()
            .join("\nUNION ALL\n"),
    )
}
