//! `sqb debug` file names, masking and wording.

pub(crate) const LOCAL_CONFIG_FILENAME: &str = "sqlbuild_local.toml";
pub(crate) const LEGACY_PROJECT_CONFIG_FILENAME: &str = "sqlbuild_project.yml";
pub(crate) const LEGACY_LOCAL_CONFIG_FILENAME: &str = "sqlbuild_local.yml";
/// Connection keys whose values are always masked.
pub(crate) const SECRET_CONNECTION_KEYS: [&str; 5] = [
    "password",
    "private_key",
    "private_key_file_pwd",
    "secret",
    "token",
];
pub(crate) const MASKED_VALUE: &str = "****";
/// Longer connection values are shortened to their first and last characters.
pub(crate) const PREVIEW_CHARACTER_LIMIT: usize = 32;
pub(crate) const PREVIEW_EDGE_CHARACTERS: usize = 4;
pub(crate) const NOT_CONFIGURED: &str = "not configured";
pub(crate) const NOT_PRESENT: &str = "not present";
pub(crate) const HEADER: &str = "SQLBuild Diagnostics";
pub(crate) const CONNECTION_TEST_LABEL: &str = "connection test";
pub(crate) const QUERY_TEST_LABEL: &str = "query test";
/// The code recorded when `sqb debug` cannot connect.
pub(crate) const CONNECTION_FAILED_CODE: &str = "C980";
/// The code recorded when `sqb debug` connects but `SELECT 1` fails.
pub(crate) const QUERY_FAILED_CODE: &str = "C981";
/// The code recorded when another `sqb debug` check fails.
pub(crate) const DEBUG_CHECK_FAILED_CODE: &str = "C982";
