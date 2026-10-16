//! Python modules, names and messages of migration state rows.

pub(crate) const OLD_NAME_VIEW_CONFIG_KEY: &str = "old_name_view";
pub(crate) const MODEL_KIND: &str = "model";
pub(crate) const COLUMN_KIND: &str = "column";
pub(crate) const OLD_NAME_KIND: &str = "old_name";
pub(crate) const MIGRATION_LOGGER: &str = "sqlbuild.migrations";
pub(crate) const LOGGING_MODULE: &str = "logging";
pub(crate) const TIME_MODULE: &str = "time";
pub(crate) const MIGRATION_WRITE_ATTEMPTS: i64 = 3;
pub(crate) const MIGRATION_WRITE_RETRY_BASE_SECONDS: f64 = 0.05;
pub(crate) const MIGRATION_WRITE_RETRY_MESSAGE: &str =
    "migration event write attempt %s/%s failed for '%s'; retrying: %s";
