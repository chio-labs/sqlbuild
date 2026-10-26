//! dlt destination defaults, adapters and the keys SQLBuild owns.

/// The integration loader name dlt connection errors cite.
pub(crate) const DLT_LOADER: &str = "dlt";
/// Destination options SQLBuild passes unless the destination config overrides them.
pub const DEFAULT_DESTINATION_OPTIONS: [(&str, &str); 1] = [("naming_convention", "sql_ci_v1")];
/// Destination config keys SQLBuild sets itself.
pub(crate) const SQLBUILD_OWNED_DESTINATION_KEYS: [&str; 4] = [
    "credentials",
    "dataset_name",
    "default_schema_name",
    "project_id",
];
/// The dataset DuckDB destinations land in without an explicit one.
pub(crate) const DUCKDB_DEFAULT_DATASET: &str = "main";
/// The dataset of SQLite's own database file; dlt attaches a file per other dataset.
pub(crate) const SQLITE_MAIN_DATASET: &str = "main";
/// The suffix Snowflake account and host settings drop.
pub(crate) const SNOWFLAKE_ACCOUNT_SUFFIX: &str = ".snowflakecomputing.com";
/// SQL Server's default port number.
pub(crate) const SQLSERVER_DEFAULT_PORT: i64 = 1433;
/// Snowflake settings copied into credentials when set, in order.
pub(crate) const SNOWFLAKE_OPTIONAL_SETTINGS: [&str; 4] =
    ["password", "role", "authenticator", "token"];
/// BigQuery factory arguments and the connection settings they come from, in order.
pub(crate) const BIGQUERY_ARGUMENTS: [(&str, &str); 2] =
    [("project_id", "project"), ("location", "location")];
pub(crate) const DUCKDB_ADAPTER: &str = "duckdb";
pub(crate) const SQLITE_ADAPTER: &str = "sqlite";
/// The dlt destination factory that writes SQLite through SQLAlchemy.
pub(crate) const SQLALCHEMY_FACTORY: &str = "sqlalchemy";
pub(crate) const MOTHERDUCK_ADAPTER: &str = "motherduck";
pub(crate) const POSTGRES_ADAPTER: &str = "postgres";
pub(crate) const SNOWFLAKE_ADAPTER: &str = "snowflake";
pub(crate) const BIGQUERY_ADAPTER: &str = "bigquery";
pub(crate) const DATABRICKS_ADAPTER: &str = "databricks";
pub(crate) const SQLSERVER_ADAPTER: &str = "sqlserver";
/// The dlt destination factory of SQL Server.
pub(crate) const SQLSERVER_FACTORY: &str = "mssql";
/// The factory argument holding destination credentials.
pub(crate) const CREDENTIALS_ARGUMENT: &str = "credentials";
