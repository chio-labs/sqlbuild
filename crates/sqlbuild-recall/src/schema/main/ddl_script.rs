//! `ddl_script`: the complete ordered script an administrator runs to create a Recall store.

use crate::schema::_helpers::rendering::clickhouse_table;
use crate::schema::constants::{
    DDL_SCRIPT_INVOCATION, META_SCHEMA_COMPONENT, META_SCHEMA_VERSION_KEY, RECALL_SCHEMA_VERSION,
};
use crate::schema::main::table_spec::table_spec;
use crate::schema::main::table_statements::table_statements;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{DdlOptions, Dialect, Table};

/// The `recall_meta` row recording the schema version, so writers allowed only `SELECT` and `INSERT` find the store complete.
fn clickhouse_version_row(options: &DdlOptions) -> String {
    format!(
        "INSERT INTO {meta} (component, key, value, recorded_at, invocation_id, \
         invocation_started_at, schema_version, producer_version, ingested_at, content_hash)\n\
         SELECT '{META_SCHEMA_COMPONENT}', '{META_SCHEMA_VERSION_KEY}', \
         '{RECALL_SCHEMA_VERSION}', now64(6), '{DDL_SCRIPT_INVOCATION}', now64(6), \
         {RECALL_SCHEMA_VERSION}, '{version}', now64(6), ''",
        meta = clickhouse_table(table_spec(Table::Meta).name, options),
        version = env!("CARGO_PKG_VERSION"),
    )
}

/// Every table, index and view statement, then for ClickHouse the schema version row, each terminated by `;`.
#[must_use]
pub fn ddl_script(dialect: Dialect, options: &DdlOptions) -> String {
    let mut statements: Vec<String> = table_statements(dialect, options);
    statements.extend(
        view_statements(dialect, options)
            .into_iter()
            .map(|(_, statement)| statement),
    );
    if dialect == Dialect::ClickHouse {
        statements.push(clickhouse_version_row(options));
    }
    let mut script: String = statements.join(";\n\n");
    script.push_str(";\n");
    script
}
