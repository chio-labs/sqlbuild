//! dbt profile output keys SQLBuild reads and the wording of unsupported profiles.

pub(crate) const MEMORY_DATABASE: &str = ":memory:";
pub(crate) const DEFAULT_DATABRICKS_CATALOG: &str = "hive_metastore";
pub(crate) const DATABRICKS_PAT_AUTH_TYPE: &str = "pat";
pub(crate) const SQLSERVER_SQL_AUTHENTICATION: &str = "sql";
pub(crate) const BIGQUERY_SUPPORTED_METHODS: [&str; 2] = ["oauth", "service-account"];
pub(crate) const BIGQUERY_UNSUPPORTED_METHODS: [&str; 3] = [
    "oauth-secrets",
    "service-account-json",
    "external-oauth-wif",
];
pub(crate) const DUCKDB_COPIED_KEYS: [&str; 3] = ["extensions", "settings", "attach"];
pub(crate) const DUCKDB_UNSUPPORTED_KEYS: [&str; 12] = [
    "config_options",
    "disable_transactions",
    "external_root",
    "filesystems",
    "is_ducklake",
    "keep_open",
    "module_paths",
    "plugins",
    "remote",
    "retries",
    "secrets",
    "use_credential_provider",
];
pub(crate) const POSTGRES_COPIED_KEYS: [&str; 11] = [
    "host",
    "port",
    "user",
    "connect_timeout",
    "role",
    "keepalives_idle",
    "sslmode",
    "sslcert",
    "sslkey",
    "sslrootcert",
    "application_name",
];
pub(crate) const SNOWFLAKE_DROPPED_KEYS: [&str; 2] = ["type", "threads"];
pub(crate) const DATABRICKS_OAUTH_KEYS: [&str; 6] = [
    "client_id",
    "client_secret",
    "azure_client_id",
    "azure_client_secret",
    "oauth_redirect_url",
    "oauth_scopes",
];
pub(crate) const BIGQUERY_METHOD_ERROR_SUFFIX: &str = "is not supported by SQLBuild dbt-profile normalization yet. Supported methods: oauth, service-account";

/// The dbt target path used when `dbt_project.yml` sets none.
pub(crate) const DEFAULT_DBT_TARGET_PATH: &str = "target";
/// Text dbt's `as_bool` reads as true, after stripping and lowercasing.
pub(crate) const DBT_TRUE_VALUES: [&str; 5] = ["true", "1", "yes", "y", "on"];
/// Text dbt's `as_bool` reads as false, after stripping and lowercasing.
pub(crate) const DBT_FALSE_VALUES: [&str; 5] = ["false", "0", "no", "n", "off"];
/// The separator that makes dbt's `as_number` read text as a float.
pub(crate) const DBT_NUMBER_DECIMAL_SEPARATOR: char = '.';
