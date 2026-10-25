//! The ingestr destination URI for a SQLBuild warehouse connection.

use crate::ingestr_command::_helpers::destinations::{
    bigquery, databricks, duckdb, motherduck, postgres, snowflake, sqlite, sqlserver,
};
use crate::ingestr_command::errors::IngestrCommandError;
use crate::loader_connection::models::LoaderConnection;

/// The ingestr destination URI for the connection of the adapter named `adapter_name`.
pub fn ingestr_destination_uri(
    adapter_name: &str,
    connection: &LoaderConnection,
) -> Result<String, IngestrCommandError> {
    match adapter_name {
        "duckdb" => duckdb(connection),
        "sqlite" => sqlite(connection),
        "motherduck" => Ok(motherduck(connection)),
        "postgres" => postgres(connection),
        "bigquery" => bigquery(connection),
        "snowflake" => snowflake(connection),
        "databricks" => databricks(connection),
        "sqlserver" => Ok(sqlserver(connection)),
        _ => Err(IngestrCommandError {
            message: format!(
                "Adapter '{adapter_name}' does not support ingestr integration loaders"
            ),
        }),
    }
}
