//! Migration decision vocabularies.

/// Model decisions that clone the origin over the destination.
pub(crate) const MOVING_DECISIONS: [&str; 4] =
    ["migrate", "redo", "superseded_replace", "forced_replace"];
/// Model decisions that stop a build regardless of compatibility.
pub(crate) const BLOCKING_DECISIONS: [&str; 2] = ["conflict", "origin_missing"];
pub(crate) const CONFLICT_DECISION: &str = "conflict";
/// Column decisions that append a column migration event.
pub(crate) const RECORDING_COLUMN_DECISIONS: [&str; 2] = ["rename", "record"];
pub(crate) const RENAME_COLUMN_DECISION: &str = "rename";
/// Column decisions that stop a build before any execution.
pub(crate) const BLOCKING_COLUMN_DECISIONS: [&str; 4] = [
    "conflict",
    "source_missing",
    "still_produced",
    "unsupported",
];
/// Plan labels of the column decisions.
pub(crate) const COLUMN_DECISION_LABELS: [(&str, &str); 7] = [
    ("rename", "rename in place"),
    ("record", "already renamed, record"),
    ("done", "done"),
    ("conflict", "conflict"),
    ("source_missing", "source missing"),
    ("still_produced", "source still produced"),
    ("unsupported", "unsupported"),
];
/// Snowflake table types by whether the table is transient.
pub(crate) const STORAGE_LABELS: [&str; 2] = ["permanent", "transient"];
