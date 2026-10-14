//! dbt event names, levels and statuses the stream reads.

pub(crate) const NODE_FINISHED_EVENT: &str = "NodeFinished";
pub(crate) const NODE_MESSAGE_EVENT_NAMES: [&str; 4] = [
    "RunResultError",
    "RunResultFailure",
    "RunResultWarning",
    "GenericExceptionOnRun",
];
pub(crate) const NODE_MESSAGE_LEVELS: [&str; 2] = ["warn", "error"];
pub(crate) const NODE_STARTED_EVENT_NAMES: [&str; 2] = ["LogStartLine", "NodeStarted"];
pub(crate) const RESULT_EVENT_NAMES: [&str; 7] = [
    "LogModelResult",
    "LogSeedResult",
    "LogSnapshotResult",
    "LogTestResult",
    "LogBatchResult",
    "LogFunctionResult",
    "NodeFinished",
];
pub(crate) const OUTCOME_STATUSES: [&str; 11] = [
    "error", "fail", "failed", "ok", "pass", "passed", "skip", "skipped", "success", "warn",
    "warning",
];
pub(crate) const START_STATUS: &str = "start";
pub(crate) const UNKNOWN_STATUS: &str = "unknown";
pub(crate) const DEFAULT_RESOURCE_TYPE: &str = "node";
pub(crate) const DEFAULT_MESSAGE_LEVEL: &str = "info";
pub(crate) const WARN_LEVEL: &str = "warn";
pub(crate) const ERROR_LEVEL: &str = "error";
/// Display labels by the dbt statuses that map to them.
pub(crate) const DISPLAY_STATUSES: [(&[&str], &str); 6] = [
    (&["ok", "success"], "OK"),
    (&["pass", "passed"], "PASS"),
    (&["warn", "warning"], "WARN"),
    (&["skip", "skipped"], "SKIP"),
    (&["error", "fail", "failed"], "FAIL"),
    (&["start"], "START"),
];
pub(crate) const RESOURCE_TYPE_WIDTH: usize = 9;
pub(crate) const NAME_WIDTH: usize = 30;
pub(crate) const COUNTER_WIDTH: usize = 5;
pub(crate) const STATUS_WIDTH: usize = 6;
pub(crate) const DURATION_WIDTH: usize = 7;
pub(crate) const MESSAGE_STATUS_WIDTH: usize = 9;
pub(crate) const MAX_LISTED_ACTIVE_NODES: usize = 3;
