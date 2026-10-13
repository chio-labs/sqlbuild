//! Lifecycle event types the terminal index distinguishes.

/// Event types that end one resource attempt.
pub(crate) const RESOURCE_TERMINALS: [&str; 3] = [
    "resource_attempt_completed",
    "resource_attempt_failed",
    "resource_attempt_skipped",
];
pub(crate) const RUN_TERMINALS: [&str; 2] = ["run_completed", "run_failed"];
pub(crate) const INVOCATION_TERMINALS: [&str; 2] = ["invocation_completed", "invocation_failed"];
pub(crate) const OPERATION_TERMINALS: [&str; 2] = ["operation_completed", "operation_failed"];
/// Operations whose terminal stands for the whole command's outcome.
pub(crate) const AGGREGATE_OPERATION_NAMES: [&str; 3] =
    ["clone_execution", "scenario_capture", "scenario_execution"];
pub(crate) const FAILED_SUFFIX: &str = "failed";
