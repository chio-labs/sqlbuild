//! Destination credentials per warehouse adapter.

use crate::dlt_destination::constants::{
    BIGQUERY_ADAPTER, BIGQUERY_ARGUMENTS, CREDENTIALS_ARGUMENT, DATABRICKS_ADAPTER, DLT_LOADER,
    MOTHERDUCK_ADAPTER, POSTGRES_ADAPTER, SNOWFLAKE_ACCOUNT_SUFFIX, SNOWFLAKE_ADAPTER,
    SNOWFLAKE_OPTIONAL_SETTINGS, SQLSERVER_ADAPTER, SQLSERVER_DEFAULT_PORT, SQLSERVER_FACTORY,
};
use crate::dlt_destination::errors::DltDestinationError;
use crate::dlt_destination::models::DltValue;
use crate::loader_connection::constants::{DEFAULT_HOST, MOTHERDUCK_PREFIX, POSTGRES_DEFAULT_PORT};
use crate::loader_connection::main::connection_setting::connection_setting;
use crate::loader_connection::main::required_connection_setting::required_connection_setting;
use crate::loader_connection::models::LoaderConnection;

/// Factory arguments, in call order.
type Arguments = Vec<(&'static str, DltValue)>;

/// A required stripped connection setting of `adapter`.
pub(crate) fn required<'a>(
    connection: &'a LoaderConnection,
    key: &str,
    adapter: &str,
) -> Result<&'a str, DltDestinationError> {
    required_connection_setting(connection, key, adapter, DLT_LOADER)
        .map_err(|message| DltDestinationError { message })
}

fn text(value: &str) -> DltValue {
    DltValue::Text(value.to_owned())
}

/// The single `credentials` argument.
pub(crate) fn credentials(value: DltValue) -> Arguments {
    vec![(CREDENTIALS_ARGUMENT, value)]
}

fn snowflake_account(account: &str) -> &str {
    account
        .strip_suffix(SNOWFLAKE_ACCOUNT_SUFFIX)
        .unwrap_or(account)
}

fn motherduck(connection: &LoaderConnection) -> DltValue {
    let database: &str = connection_setting(connection, "database").unwrap_or_default();
    let mut credentials: String = if database.starts_with(MOTHERDUCK_PREFIX) {
        database.to_owned()
    } else {
        format!("{MOTHERDUCK_PREFIX}{database}")
    };
    if let Some(token) = connection_setting(connection, "token") {
        credentials = format!("{credentials}?motherduck_token={token}");
    }
    DltValue::Text(credentials)
}

fn postgres(connection: &LoaderConnection) -> Result<DltValue, DltDestinationError> {
    let host: &str = connection_setting(connection, "host").unwrap_or(DEFAULT_HOST);
    let port: &str = connection.port.as_deref().unwrap_or(POSTGRES_DEFAULT_PORT);
    let user: &str = required(connection, "user", POSTGRES_ADAPTER)?;
    let password: &str = connection_setting(connection, "password").unwrap_or_default();
    let database: &str = match connection_setting(connection, "dbname") {
        Some(database) => database,
        None => required(connection, "database", POSTGRES_ADAPTER)?,
    };
    Ok(DltValue::Text(format!(
        "postgresql://{user}:{password}@{host}:{port}/{database}"
    )))
}

fn snowflake(connection: &LoaderConnection) -> Result<DltValue, DltDestinationError> {
    let account: &str = required(connection, "account", SNOWFLAKE_ADAPTER)?;
    let host: &str = connection_setting(connection, "host").unwrap_or(account);
    let mut fields: Arguments = vec![
        ("account", text(snowflake_account(account))),
        ("host", text(snowflake_account(host))),
        (
            "user",
            text(required(connection, "user", SNOWFLAKE_ADAPTER)?),
        ),
        (
            "database",
            text(required(connection, "database", SNOWFLAKE_ADAPTER)?),
        ),
        (
            "warehouse",
            text(required(connection, "warehouse", SNOWFLAKE_ADAPTER)?),
        ),
    ];
    for key in SNOWFLAKE_OPTIONAL_SETTINGS {
        if let Some(value) = connection_setting(connection, key) {
            fields.push((key, text(value)));
        }
    }
    Ok(DltValue::Object(fields))
}

fn bigquery(connection: &LoaderConnection) -> Arguments {
    let mut arguments: Arguments = Vec::new();
    for (argument, key) in BIGQUERY_ARGUMENTS {
        if let Some(value) = connection_setting(connection, key) {
            arguments.push((argument, text(value)));
        }
    }
    arguments
}

fn databricks(connection: &LoaderConnection) -> Result<DltValue, DltDestinationError> {
    let mut fields: Arguments = vec![
        (
            "server_hostname",
            text(required(connection, "server_hostname", DATABRICKS_ADAPTER)?),
        ),
        (
            "http_path",
            text(required(connection, "http_path", DATABRICKS_ADAPTER)?),
        ),
        (
            "access_token",
            text(required(connection, "token", DATABRICKS_ADAPTER)?),
        ),
    ];
    if let Some(catalog) = connection_setting(connection, "catalog") {
        fields.push(("catalog", text(catalog)));
    }
    Ok(DltValue::Object(fields))
}

fn sqlserver(connection: &LoaderConnection) -> Result<DltValue, DltDestinationError> {
    Ok(DltValue::Object(vec![
        (
            "host",
            text(connection_setting(connection, "host").unwrap_or(DEFAULT_HOST)),
        ),
        (
            "port",
            DltValue::Port {
                default: SQLSERVER_DEFAULT_PORT,
            },
        ),
        (
            "database",
            text(required(connection, "database", SQLSERVER_ADAPTER)?),
        ),
        (
            "username",
            text(required(connection, "user", SQLSERVER_ADAPTER)?),
        ),
        (
            "password",
            text(connection_setting(connection, "password").unwrap_or_default()),
        ),
        (
            "query",
            DltValue::Object(vec![("TrustServerCertificate", text("yes"))]),
        ),
    ]))
}

/// The factory and arguments of a non-DuckDB adapter, or `None` when dlt cannot load into it.
pub(crate) fn adapter_call(
    adapter: &str,
    connection: &LoaderConnection,
) -> Result<Option<(&'static str, Arguments)>, DltDestinationError> {
    Ok(Some(match adapter {
        MOTHERDUCK_ADAPTER => (MOTHERDUCK_ADAPTER, credentials(motherduck(connection))),
        POSTGRES_ADAPTER => (POSTGRES_ADAPTER, credentials(postgres(connection)?)),
        SNOWFLAKE_ADAPTER => (SNOWFLAKE_ADAPTER, credentials(snowflake(connection)?)),
        BIGQUERY_ADAPTER => (BIGQUERY_ADAPTER, bigquery(connection)),
        DATABRICKS_ADAPTER => (DATABRICKS_ADAPTER, credentials(databricks(connection)?)),
        SQLSERVER_ADAPTER => (SQLSERVER_FACTORY, credentials(sqlserver(connection)?)),
        _ => return Ok(None),
    }))
}
