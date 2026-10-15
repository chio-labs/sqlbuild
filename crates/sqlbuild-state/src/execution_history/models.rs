//! Execution history facts, projected runs, filters and the parameterised SQL backends run.

use crate::execution_history::types::UtcTime;

/// Which backend's SQL placeholders, cursors and column types to use.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dialect {
    Sqlite,
    Postgres,
}

/// Latest terminal status derivable from durable run facts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RunStatus {
    Unknown,
    Completed,
    Failed,
}

impl RunStatus {
    /// The `RunStatus` enum value text.
    pub fn value(self) -> &'static str {
        match self {
            Self::Unknown => "unknown",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }
}

/// Stable envelope fields stored next to one event's canonical content.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct EventEnvelope {
    pub schema_version: i64,
    /// Values of `ENVELOPE_TEXT_FIELDS`, in that order.
    pub text_fields: [Option<String>; 9],
    pub occurred_at: Option<UtcTime>,
}

/// One event to append: its required id, canonical JSON content and envelope.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EventSubmission {
    pub event_id: String,
    pub content: String,
    pub envelope: EventEnvelope,
}

/// An event ready to insert, with the SHA-256 digest of its content.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PreparedEvent {
    pub event_id: String,
    pub content: String,
    pub digest: String,
    pub envelope: EventEnvelope,
}

/// The run-correlated part of a known lifecycle event.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunFact {
    pub run_id: String,
    pub invocation_id: String,
    pub event_type: String,
    pub occurred_at: UtcTime,
}

/// One durable event as projection reads it; opaque or run-less events carry no `run`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectionFact {
    pub storage_order: i64,
    pub cursor: String,
    pub received_at: UtcTime,
    pub run: Option<RunFact>,
}

/// One projected run, as `RunRecord`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunRow {
    pub run_id: String,
    pub invocation_id: String,
    pub created_at: UtcTime,
    pub status: RunStatus,
    pub is_complete: bool,
    pub last_event_cursor: String,
    pub last_storage_order: i64,
    pub command: Option<String>,
    pub target: Option<String>,
    pub environment: Option<String>,
    pub started_at: Option<UtcTime>,
    pub ended_at: Option<UtcTime>,
}

/// A filter bound: its instant in UTC and whether its `tzinfo` is exactly `UTC`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FilterTime {
    pub instant: UtcTime,
    pub is_utc: bool,
}

/// `EventFilter` fields.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct EventFilterSpec {
    pub invocation_id: Option<String>,
    pub run_id: Option<String>,
    pub producer: Option<String>,
    pub event_types: Vec<String>,
    /// The `EventFamily` value.
    pub family: Option<String>,
    pub occurred_at_start: Option<FilterTime>,
    pub occurred_at_end: Option<FilterTime>,
}

/// `RunFilter` fields.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RunFilterSpec {
    pub invocation_id: Option<String>,
    pub statuses: Vec<RunStatus>,
    pub created_at_start: Option<FilterTime>,
    pub created_at_end: Option<FilterTime>,
}

/// An event or run filter to validate.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FilterSpec<'a> {
    Event(&'a EventFilterSpec),
    Run(&'a RunFilterSpec),
}

/// One SQL parameter; the backend glue renders timestamps for its driver.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SqlParam {
    Null,
    Text(String),
    Integer(i64),
    Flag(bool),
    Timestamp(UtcTime),
    TextList(Vec<String>),
}

/// SQL text and its parameters in placeholder order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Query {
    pub sql: String,
    pub params: Vec<SqlParam>,
}

/// A decoded run cursor's position: the stored `created_at` text and the run id.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DecodedRunCursor {
    pub created_at_text: String,
    pub run_id: String,
}

/// A validated run cursor's page position.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RunCursorKey {
    pub created_at: UtcTime,
    pub created_at_text: String,
    pub run_id: String,
}

/// `PostgresExecutionHistory` constructor settings; non-integer values are `None`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PostgresSettings {
    pub dsn: Option<String>,
    pub connect_timeout_seconds: Option<i64>,
    pub statement_timeout_ms: Option<i64>,
    pub max_transaction_retries: Option<i64>,
}

/// Where a SQLite history lives: an explicit `path`, a `project_dir`, or the working directory.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqliteLocation {
    pub project_dir: Option<String>,
    pub path: Option<String>,
    pub working_directory: String,
    /// `busy_timeout_ms`, or `None` when it is not an integer.
    pub busy_timeout_ms: Option<i64>,
}
