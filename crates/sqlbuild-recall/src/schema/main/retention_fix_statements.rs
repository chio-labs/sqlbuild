//! `retention_fix_statements`: what an administrator runs to give a ClickHouse store another retention.

use crate::schema::_helpers::rendering::{clickhouse_table, clickhouse_ttl};
use crate::schema::constants::ALL_TABLES;
use crate::schema::main::table_spec::table_spec;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{DdlOptions, Dialect, TableSpec};

/// `ALTER TABLE … MODIFY TTL` for each table named in `tables`, then the views, which filter by retention; each statement ends with `;`.
#[must_use]
pub fn retention_fix_statements(tables: &[String], options: &DdlOptions) -> String {
    let mut statements: Vec<String> = Vec::new();
    for table in ALL_TABLES {
        let spec: &TableSpec = table_spec(table);
        if tables.iter().any(|name| name == spec.name) {
            statements.push(format!(
                "ALTER TABLE {} MODIFY TTL {}",
                clickhouse_table(spec.name, options),
                clickhouse_ttl(spec, options)
            ));
        }
    }
    for (_, statement) in view_statements(Dialect::ClickHouse, options) {
        statements.push(statement);
    }
    let mut script: String = statements.join(";\n\n");
    script.push_str(";\n");
    script
}
