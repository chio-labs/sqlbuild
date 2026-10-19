//! Resolved Recall settings for one invocation.

use std::path::PathBuf;

/// Where Recall writes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StoreLocation {
    /// A SQLite file, written natively.
    Sqlite { path: PathBuf },
    /// A connection whose adapter this build cannot write Recall rows to yet.
    Unsupported { connection: String, adapter: String },
}

/// The effective settings: target, store and policies.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecallSettings {
    pub enabled: bool,
    /// The effective target; `None` for commands without one.
    pub target: Option<String>,
    pub store: StoreLocation,
    /// The configured connection name, `None` for the built-in local store.
    pub connection: Option<String>,
    pub retention_days: u32,
    pub shutdown_timeout_ms: u64,
    pub diagnostics_min_severity: String,
    pub project_name: Option<String>,
    pub project_adapter: Option<String>,
    pub destination_database: Option<String>,
    pub destination_schema: Option<String>,
}

/// What selects the settings: the project directory and the `--target` option.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SettingsRequest {
    pub project_dir: PathBuf,
    pub selected_target: Option<String>,
}
