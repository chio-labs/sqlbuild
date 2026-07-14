"""dbt profile constants."""

DBT_BIGQUERY_SUPPORTED_METHODS: frozenset[str] = frozenset({"oauth", "service-account"})
DBT_BIGQUERY_UNSUPPORTED_METHODS: frozenset[str] = frozenset(
    {"oauth-secrets", "service-account-json", "external-oauth-wif"}
)
DBT_DATABRICKS_PAT_AUTH_TYPE: str = "pat"
DBT_DUCKDB_MEMORY_DATABASE: str = ":memory:"
DBT_DUCKDB_UNSUPPORTED_PROFILE_KEYS: frozenset[str] = frozenset(
    {
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
    }
)
DBT_FALSE_VALUES: frozenset[str] = frozenset({"false", "0", "no", "n", "off"})
DBT_JINJA_MARKERS: tuple[str, ...] = ("{{", "{%", "{#")
DBT_NUMBER_DECIMAL_SEPARATOR: str = "."
DBT_PROFILE_CONNECTION_SOURCE: str = "dbt_profile"
DBT_PROFILE_HOST_KEY: str = "host"
DBT_PROFILE_HTTP_PATH_KEY: str = "http_path"
DBT_PROFILE_KEYFILE_KEY: str = "keyfile"
DBT_PROFILE_LOCATION_KEY: str = "location"
DBT_PROFILE_SCHEMA_KEY: str = "schema"
DBT_PROFILE_TOKEN_KEY: str = "token"
DBT_SQLSERVER_SQL_AUTHENTICATION: str = "sql"
DBT_TRUE_VALUES: frozenset[str] = frozenset({"true", "1", "yes", "y", "on"})
