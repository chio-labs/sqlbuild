//! `create_database_statement`: the statement that creates a ClickHouse store's database.

use crate::schema::_helpers::rendering::{clickhouse_identifier, on_cluster};
use crate::schema::models::DdlOptions;

/// `CREATE DATABASE IF NOT EXISTS` for the configured database, which leaves an existing database and its engine alone; `None` without one.
#[must_use]
pub fn create_database_statement(options: &DdlOptions) -> Option<String> {
    options.database.as_deref().map(|database| {
        format!(
            "CREATE DATABASE IF NOT EXISTS {}{}",
            clickhouse_identifier(database),
            on_cluster(options)
        )
    })
}
