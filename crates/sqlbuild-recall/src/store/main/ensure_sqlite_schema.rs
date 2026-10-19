//! `ensure_sqlite_schema`: create and additively upgrade the store's tables and views.

use crate::records::main::meta_row::meta_row;
use crate::records::models::RowEnvelope;
use crate::schema::constants::{
    META_SCHEMA_COMPONENT, META_SCHEMA_VERSION_KEY, RECALL_SCHEMA_VERSION,
};
use crate::schema::main::table_statements::table_statements;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::Dialect;
use crate::store::_helpers::rows::write_rows;
use crate::store::_helpers::schema::{add_missing_columns, current, sqlite_options};
use crate::store::_helpers::sqlite::{checked, immediate, stored_schema_version};
use crate::store::errors::StoreError;
use crate::store::models::SqliteStore;

/// Create missing tables, indexes and views, add missing columns and record the schema version, in one `BEGIN IMMEDIATE` transaction. A store written by a newer SQLBuild keeps its views.
pub fn ensure_sqlite_schema(
    store: &SqliteStore,
    envelope: &RowEnvelope,
    recorded_at: &str,
) -> Result<(), StoreError> {
    if current(&store.connection)? {
        return Ok(());
    }
    let options = sqlite_options();
    immediate(&store.connection, "create Recall tables", |connection| {
        for statement in table_statements(Dialect::Sqlite, &options) {
            checked(connection.execute_batch(&statement), "create Recall table")?;
        }
        add_missing_columns(connection)?;
        let stored: Option<i64> = stored_schema_version(connection)?;
        let upgrade: bool = stored.is_none_or(|version| version < RECALL_SCHEMA_VERSION);
        for (name, statement) in view_statements(Dialect::Sqlite, &options) {
            if upgrade {
                checked(
                    connection.execute_batch(&format!("DROP VIEW IF EXISTS \"{name}\"")),
                    "replace Recall view",
                )?;
            }
            checked(connection.execute_batch(&statement), "create Recall view")?;
        }
        if upgrade {
            let version = RECALL_SCHEMA_VERSION.to_string();
            write_rows(
                connection,
                &[meta_row(
                    envelope,
                    (META_SCHEMA_COMPONENT, META_SCHEMA_VERSION_KEY, &version),
                    recorded_at,
                )],
                recorded_at,
            )?;
        }
        Ok(())
    })
}
