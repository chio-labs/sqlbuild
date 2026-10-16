//! Ingestr command vocabulary and destination defaults.

/// The fixed leading arguments of every ingestr run.
pub(crate) const COMMAND_PREFIX: [&str; 2] = ["ingestr", "ingest"];
/// Progress reporting arguments ingestr runs with.
pub(crate) const COMMAND_PROGRESS: [&str; 3] = ["--yes", "--progress", "log"];
/// Characters Python's `urllib.parse.quote` never escapes.
pub(crate) const URL_ALWAYS_SAFE: &[u8] = b"_.-~";
/// SQL Server's default port.
pub(crate) const SQLSERVER_DEFAULT_PORT: &str = "1433";
/// The SQL Server ODBC driver ingestr uses unless the connection names one.
pub(crate) const SQLSERVER_DEFAULT_DRIVER: &str = "ODBC Driver 18 for SQL Server";
/// Optional BigQuery query parameters, in URI order.
pub(crate) const BIGQUERY_PARAMETERS: [&str; 3] =
    ["location", "credentials_path", "credentials_base64"];
/// Optional Snowflake query parameters, in URI order.
pub(crate) const SNOWFLAKE_PARAMETERS: [&str; 6] = [
    "warehouse",
    "role",
    "token",
    "private_key",
    "private_key_passphrase",
    "authenticator",
];
/// Optional Databricks query parameters after `http_path`, in URI order.
pub(crate) const DATABRICKS_PARAMETERS: [&str; 2] = ["catalog", "schema"];
/// Optional SQL Server query parameters, in URI order.
pub(crate) const SQLSERVER_PARAMETERS: [&str; 3] =
    ["driver", "TrustServerCertificate", "Authentication"];
/// The SQL Server driver query parameter.
pub(crate) const SQLSERVER_DRIVER_PARAMETER: &str = "driver";
/// The SQL Server certificate trust query parameter.
pub(crate) const SQLSERVER_TRUST_SERVER_CERTIFICATE_PARAMETER: &str = "TrustServerCertificate";
/// The integration loader name ingestr connection errors cite.
pub(crate) const INGESTR_LOADER: &str = "ingestr";
