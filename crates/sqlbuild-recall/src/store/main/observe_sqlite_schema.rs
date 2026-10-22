//! `observe_sqlite_schema`: the tables, columns, views and schema version a SQLite store holds, read without writing.

use std::collections::BTreeSet;

use crate::schema::constants::ALL_TABLES;
use crate::schema::main::table_spec::table_spec;
use crate::schema::models::ObservedSchema;
use crate::store::_helpers::schema::stored_columns;
use crate::store::_helpers::sqlite::{checked, stored_schema_version};
use crate::store::constants::SQLITE_VIEW_TYPE;
use crate::store::errors::StoreError;
use crate::store::models::SqliteStore;

/// The store's Recall tables with their columns, its views and its recorded schema version.
pub fn observe_sqlite_schema(store: &SqliteStore) -> Result<ObservedSchema, StoreError> {
    let connection = &store.connection;
    let mut statement = checked(
        connection.prepare("SELECT type, name FROM sqlite_schema WHERE type IN ('table', 'view')"),
        "inspect Recall store",
    )?;
    let objects: Vec<(String, String)> = checked(
        statement
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
            .and_then(Iterator::collect),
        "inspect Recall store",
    )?;
    let mut observed = ObservedSchema::default();
    for (kind, name) in objects {
        if kind == SQLITE_VIEW_TYPE {
            observed.views.insert(name);
        } else if let Some(table) = ALL_TABLES
            .iter()
            .find(|table| table_spec(**table).name == name)
        {
            let columns: BTreeSet<String> =
                stored_columns(connection, *table)?.into_iter().collect();
            observed.tables.insert(*table, columns);
        }
    }
    observed.version = stored_schema_version(connection)?;
    Ok(observed)
}
