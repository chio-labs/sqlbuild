//! Per-adapter normalization of a rendered dbt profile output.

use crate::dbt_profile::_helpers::output::Output;
use crate::dbt_profile::constants::{
    BIGQUERY_METHOD_ERROR_SUFFIX, BIGQUERY_SUPPORTED_METHODS, BIGQUERY_UNSUPPORTED_METHODS,
    DATABRICKS_OAUTH_KEYS, DATABRICKS_PAT_AUTH_TYPE, DEFAULT_DATABRICKS_CATALOG,
    DUCKDB_COPIED_KEYS, DUCKDB_UNSUPPORTED_KEYS, MEMORY_DATABASE, POSTGRES_COPIED_KEYS,
    SNOWFLAKE_DROPPED_KEYS, SQLSERVER_SQL_AUTHENTICATION,
};
use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::{ConnectionKey, ConnectionSource, NormalizedProfile};

fn normalized(
    adapter: &'static str,
    connection: Vec<(ConnectionKey, ConnectionSource)>,
) -> NormalizedProfile {
    NormalizedProfile {
        adapter,
        connection,
        target_schema: None,
        target_database: None,
        warnings: Vec::new(),
    }
}

fn copied(output: &Output<'_>, keys: &[&'static str]) -> Vec<(ConnectionKey, ConnectionSource)> {
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> = Vec::new();
    for key in keys {
        if let Some(index) = output.index(key) {
            connection.push((ConnectionKey::Name(key), ConnectionSource::Entry(index)));
        }
    }
    connection
}

fn renamed(
    output: &Output<'_>,
    (from, to): (&str, &'static str),
) -> Option<(ConnectionKey, ConnectionSource)> {
    output
        .index(from)
        .map(|index| (ConnectionKey::Name(to), ConnectionSource::Entry(index)))
}

pub(crate) fn duckdb(output: &Output<'_>) -> NormalizedProfile {
    let database: ConnectionSource = output
        .first_value(&["path"])
        .or_else(|| output.first_value(&["database"]))
        .map_or(
            ConnectionSource::Text(MEMORY_DATABASE),
            ConnectionSource::Entry,
        );
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> =
        vec![(ConnectionKey::Name("database"), database)];
    connection.extend(copied(output, &DUCKDB_COPIED_KEYS));
    let unsupported: Vec<String> = output.sorted_present(&DUCKDB_UNSUPPORTED_KEYS, false);
    let mut profile: NormalizedProfile = normalized("duckdb", connection);
    if !unsupported.is_empty() {
        profile.warnings.push(format!(
            "dbt-duckdb profile fields are not applied by SQLBuild yet: {}",
            unsupported.join(", ")
        ));
    }
    profile.target_schema = output.text_at(output.index("schema"));
    profile.target_database = output.text_at(output.index("database"));
    profile
}

pub(crate) fn postgres(output: &Output<'_>) -> NormalizedProfile {
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> =
        copied(output, &POSTGRES_COPIED_KEYS);
    if let Some(index) = output.first_value(&["dbname", "database"]) {
        connection.push((
            ConnectionKey::Name("dbname"),
            ConnectionSource::Entry(index),
        ));
    }
    if let Some(index) = output.first_value(&["pass", "password"]) {
        connection.push((
            ConnectionKey::Name("password"),
            ConnectionSource::Entry(index),
        ));
    }
    let mut profile: NormalizedProfile = normalized("postgres", connection);
    profile.target_schema = output.non_empty_text(&["schema"]);
    profile
}

pub(crate) fn snowflake(output: &Output<'_>) -> NormalizedProfile {
    let connection: Vec<(ConnectionKey, ConnectionSource)> = output
        .0
        .iter()
        .enumerate()
        .filter(|(_, entry)| {
            !entry
                .key
                .as_deref()
                .is_some_and(|key| SNOWFLAKE_DROPPED_KEYS.contains(&key))
        })
        .map(|(index, _)| (ConnectionKey::Entry(index), ConnectionSource::Entry(index)))
        .collect();
    let mut profile: NormalizedProfile = normalized("snowflake", connection);
    profile.target_schema = output.non_empty_text(&["schema"]);
    profile.target_database = output.non_empty_text(&["database"]);
    profile
}

fn bigquery_method_error(method: &str) -> DbtProfileError {
    DbtProfileError(format!(
        "dbt BigQuery profile method '{method}' {BIGQUERY_METHOD_ERROR_SUFFIX}"
    ))
}

pub(crate) fn bigquery(output: &Output<'_>) -> Result<NormalizedProfile, DbtProfileError> {
    let method: Option<String> = output.non_empty_text(&["method"]);
    if let Some(method) = &method
        && BIGQUERY_UNSUPPORTED_METHODS.contains(&method.as_str())
    {
        return Err(bigquery_method_error(method));
    }
    let project: Option<usize> = output.first_value(&["project", "database"]);
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> = Vec::new();
    if let Some(index) = project {
        connection.push((
            ConnectionKey::Name("project"),
            ConnectionSource::Entry(index),
        ));
    }
    connection.extend(renamed(output, ("location", "location")));
    connection.extend(renamed(output, ("keyfile", "credentials_path")));
    if let Some(method) = &method
        && !BIGQUERY_SUPPORTED_METHODS.contains(&method.as_str())
    {
        return Err(bigquery_method_error(method));
    }
    let mut profile: NormalizedProfile = normalized("bigquery", connection);
    profile.target_schema = output.non_empty_text(&["dataset", "schema"]);
    profile.target_database = output.text_at(project).filter(|text| !text.is_empty());
    Ok(profile)
}

pub(crate) fn databricks(output: &Output<'_>) -> Result<NormalizedProfile, DbtProfileError> {
    let unsupported: Vec<String> = output.sorted_present(&DATABRICKS_OAUTH_KEYS, true);
    if let Some(auth_type) = output.non_empty_text(&["auth_type"])
        && auth_type != DATABRICKS_PAT_AUTH_TYPE
    {
        return Err(DbtProfileError(format!(
            "dbt Databricks profile auth_type '{auth_type}' is not supported by SQLBuild dbt-profile normalization yet. Supported auth: personal access token"
        )));
    }
    if !unsupported.is_empty() {
        return Err(DbtProfileError(format!(
            "dbt Databricks OAuth/Azure profile fields are not supported by SQLBuild dbt-profile normalization yet: {}",
            unsupported.join(", ")
        )));
    }
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> = Vec::new();
    connection.extend(renamed(output, ("host", "server_hostname")));
    connection.extend(renamed(output, ("http_path", "http_path")));
    connection.extend(renamed(output, ("token", "token")));
    let catalog: Option<usize> = output.first_value(&["catalog", "database"]);
    connection.push((
        ConnectionKey::Name("catalog"),
        catalog.map_or(
            ConnectionSource::Text(DEFAULT_DATABRICKS_CATALOG),
            ConnectionSource::Entry,
        ),
    ));
    connection.extend(renamed(output, ("schema", "schema")));
    let mut profile: NormalizedProfile = normalized("databricks", connection);
    profile.target_schema = output.non_empty_text(&["schema"]);
    profile.target_database = match catalog {
        Some(index) => output.text_at(Some(index)).filter(|text| !text.is_empty()),
        None => Some(DEFAULT_DATABRICKS_CATALOG.to_owned()),
    };
    Ok(profile)
}

pub(crate) fn sqlserver(output: &Output<'_>) -> Result<NormalizedProfile, DbtProfileError> {
    if output.is_true("windows_login") || output.is_true("trusted_connection") {
        return Err(DbtProfileError(
            "dbt SQL Server Windows authentication is not supported by SQLBuild dbt-profile normalization yet"
                .to_owned(),
        ));
    }
    if let Some(authentication) = output.non_empty_text(&["authentication", "auth"])
        && authentication.to_lowercase() != SQLSERVER_SQL_AUTHENTICATION
    {
        return Err(DbtProfileError(format!(
            "dbt SQL Server authentication mode '{authentication}' is not supported by SQLBuild dbt-profile normalization yet. Supported authentication: sql"
        )));
    }
    let values: [(&'static str, Option<usize>); 5] = [
        ("host", output.first_value(&["server", "host"])),
        ("port", output.first_value(&["port"])),
        ("user", output.first_value(&["UID", "user", "username"])),
        ("password", output.first_value(&["PWD", "password", "pass"])),
        ("database", output.first_value(&["database"])),
    ];
    let mut connection: Vec<(ConnectionKey, ConnectionSource)> = Vec::new();
    for (key, index) in values {
        if let Some(index) = index {
            connection.push((ConnectionKey::Name(key), ConnectionSource::Entry(index)));
        }
    }
    let mut profile: NormalizedProfile = normalized("sqlserver", connection);
    profile.target_schema = output.non_empty_text(&["schema"]);
    Ok(profile)
}
