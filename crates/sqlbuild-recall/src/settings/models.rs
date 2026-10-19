//! Resolved Recall settings for one invocation.

use std::path::PathBuf;

use sqlbuild_config::models::ConfigValue;

use crate::settings::constants::DEFAULT_SQLITE_MAX_OUTPUT_BYTES;

/// Where Recall writes.
#[derive(Clone, Debug, PartialEq)]
pub enum StoreLocation {
    /// A SQLite file, written natively.
    Sqlite { path: PathBuf },
    /// An existing ClickHouse database, written through the ClickHouse adapter's connection.
    ClickHouse {
        connection: String,
        /// The connection options `connect()` receives: `adapter` removed, `${env:...}` expanded.
        config: Vec<(String, ConfigValue)>,
        database: String,
    },
    /// A connection whose adapter this build cannot write Recall rows to yet.
    Unsupported { connection: String, adapter: String },
}

impl StoreLocation {
    /// The per-stream output limit when none is configured: bounded for the local file, which every command writes; a ClickHouse store, sized by its operator, records everything.
    #[must_use]
    pub fn default_max_output_bytes(&self) -> Option<u64> {
        match self {
            Self::Sqlite { .. } => Some(DEFAULT_SQLITE_MAX_OUTPUT_BYTES),
            Self::ClickHouse { .. } | Self::Unsupported { .. } => None,
        }
    }
}

/// The effective settings: target, store and policies.
#[derive(Clone, Debug, PartialEq)]
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
    /// Bytes of each output stream recorded, half from its start and half from its end; `None` records everything.
    pub max_output_bytes: Option<u64>,
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
