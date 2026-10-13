//! Load selection graphs, entries and results.

/// The managed sources and loader functions selection works over.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LoadGraph {
    /// Managed sources in declaration order, with the loader each runs.
    pub sources: Vec<(String, String)>,
    /// Loader functions in discovery order, with the loaders each depends on.
    pub loaders: Vec<(String, Vec<String>)>,
}

/// One entry `sqb load` runs, in execution order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LoadEntry {
    /// An intermediate loader that no selected source runs.
    Loader(String),
    /// A managed source.
    Source(String),
}

/// How one load ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LoadStatus {
    Success,
    Skipped,
    Failed,
}

impl LoadStatus {
    /// The status from its `ExecutionStatus` value; anything unknown counts as failed.
    #[must_use]
    pub fn from_value(value: &str) -> Self {
        match value {
            "success" => Self::Success,
            "skipped" => Self::Skipped,
            _ => Self::Failed,
        }
    }
}

/// One load result as the command renders it.
#[derive(Clone, Debug, PartialEq)]
pub struct LoadResultText {
    pub source_name: String,
    pub loader_name: String,
    /// The `ExecutionResourceKind` value, such as `source` or `loader`.
    pub resource_kind: String,
    pub status: LoadStatus,
    pub rows_loaded: i64,
    pub duration_ms: Option<f64>,
    /// Messages of the result's log lifecycle events.
    pub log_messages: Vec<String>,
    pub error_message: Option<String>,
    pub warning_messages: Vec<String>,
}

/// Result counts of one load run.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct LoadCounts {
    pub pass: i64,
    pub warn: i64,
    pub fail: i64,
    pub skip: i64,
    pub total: i64,
}

/// The source a spinner row shows: position, kind, name and the latest loader message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoadSpinnerRow {
    pub ordinal: i64,
    pub total: i64,
    pub resource_kind: String,
    pub name: String,
    pub message: String,
}
