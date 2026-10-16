//! Destination URIs per warehouse adapter.

use crate::ingestr_command::_helpers::connection::{optional, present, required};
use crate::ingestr_command::_helpers::url_quote::{query_suffix, quote, urlencode};
use crate::ingestr_command::constants::{
    BIGQUERY_PARAMETERS, DATABRICKS_PARAMETERS, SNOWFLAKE_PARAMETERS, SQLSERVER_DEFAULT_DRIVER,
    SQLSERVER_DEFAULT_PORT, SQLSERVER_DRIVER_PARAMETER, SQLSERVER_PARAMETERS,
    SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER,
};
use crate::ingestr_command::errors::IngestrCommandError;
use crate::loader_connection::constants::{DEFAULT_HOST, MOTHERDUCK_PREFIX, POSTGRES_DEFAULT_PORT};
use crate::loader_connection::models::LoaderConnection;

/// DuckDB's database file URI.
pub(crate) fn duckdb(connection: &LoaderConnection) -> Result<String, IngestrCommandError> {
    Ok(format!(
        "duckdb:///{}",
        required(connection, "database", "duckdb")?
    ))
}

/// MotherDuck's database URI with its optional token.
pub(crate) fn motherduck(connection: &LoaderConnection) -> String {
    let database: &str = optional(connection, "database").unwrap_or_default();
    let database: &str = database.strip_prefix(MOTHERDUCK_PREFIX).unwrap_or(database);
    let token: Vec<(&str, &str)> = optional(connection, "token")
        .map(|token| ("token", token))
        .into_iter()
        .collect();
    format!("motherduck://{}{}", quote(database), query_suffix(&token))
}

/// Postgres's URI with its optional SSL mode.
pub(crate) fn postgres(connection: &LoaderConnection) -> Result<String, IngestrCommandError> {
    let host: &str = optional(connection, "host").unwrap_or(DEFAULT_HOST);
    let port: &str = connection.port.as_deref().unwrap_or(POSTGRES_DEFAULT_PORT);
    let user: &str = required(connection, "user", "postgres")?;
    let password: &str = optional(connection, "password").unwrap_or_default();
    let database: &str = match optional(connection, "dbname") {
        Some(database) => database,
        None => required(connection, "database", "postgres")?,
    };
    let sslmode: Vec<(&str, &str)> = present(connection, &["sslmode"]);
    Ok(format!(
        "postgresql://{}:{}@{host}:{port}/{}{}",
        quote(user),
        quote(password),
        quote(database),
        query_suffix(&sslmode)
    ))
}

/// BigQuery's project URI with its optional credentials.
pub(crate) fn bigquery(connection: &LoaderConnection) -> Result<String, IngestrCommandError> {
    let project: &str = match optional(connection, "project") {
        Some(project) => project,
        None => required(connection, "database", "bigquery")?,
    };
    Ok(format!(
        "bigquery://{project}{}",
        query_suffix(&present(connection, &BIGQUERY_PARAMETERS))
    ))
}

/// Snowflake's account URI with its optional session settings.
pub(crate) fn snowflake(connection: &LoaderConnection) -> Result<String, IngestrCommandError> {
    let account: &str = required(connection, "account", "snowflake")?;
    let user: &str = required(connection, "user", "snowflake")?;
    let password: &str = optional(connection, "password").unwrap_or_default();
    let database: &str = required(connection, "database", "snowflake")?;
    let schema: &str = required(connection, "schema", "snowflake")?;
    Ok(format!(
        "snowflake://{}:{}@{account}/{}/{}{}",
        quote(user),
        quote(password),
        quote(database),
        quote(schema),
        query_suffix(&present(connection, &SNOWFLAKE_PARAMETERS))
    ))
}

/// Databricks's token URI with its warehouse path.
pub(crate) fn databricks(connection: &LoaderConnection) -> Result<String, IngestrCommandError> {
    let host: &str = required(connection, "server_hostname", "databricks")?;
    let token: &str = required(connection, "token", "databricks")?;
    let mut parameters: Vec<(&str, &str)> = vec![(
        "http_path",
        required(connection, "http_path", "databricks")?,
    )];
    parameters.extend(present(connection, &DATABRICKS_PARAMETERS));
    Ok(format!(
        "databricks://token:{}@{host}?{}",
        quote(token),
        urlencode(&parameters)
    ))
}

/// SQL Server's URI with its ODBC defaults.
pub(crate) fn sqlserver(connection: &LoaderConnection) -> String {
    let first = |keys: [&str; 2], default: &'static str| -> String {
        keys.iter()
            .find_map(|key| optional(connection, key))
            .unwrap_or(default)
            .to_owned()
    };
    let host: String = first(["host", "server"], DEFAULT_HOST);
    let port: &str = connection.port.as_deref().unwrap_or(SQLSERVER_DEFAULT_PORT);
    let user: String = first(["user", "username"], "sa");
    let password: &str = optional(connection, "password").unwrap_or_default();
    let database: String = first(["database", "dbname"], "master");
    let mut parameters: Vec<(&str, &str)> = present(connection, &SQLSERVER_PARAMETERS);
    let defaults: [(&str, &str); 2] = [
        (SQLSERVER_DRIVER_PARAMETER, SQLSERVER_DEFAULT_DRIVER),
        (SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER, "yes"),
    ];
    for (key, value) in defaults {
        if !parameters
            .iter()
            .any(|(present_key, _)| *present_key == key)
        {
            parameters.push((key, value));
        }
    }
    format!(
        "mssql://{}:{}@{host}:{port}/{}{}",
        quote(&user),
        quote(password),
        quote(&database),
        query_suffix(&parameters)
    )
}
