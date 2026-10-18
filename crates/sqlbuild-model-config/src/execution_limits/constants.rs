//! Execution-limit header keys and values.

/// The TEST() and SCENARIO() header key for a per-item timeout.
pub const TIMEOUT_KEY: &str = "timeout";
/// The MODEL() header and defaults key for a per-model execution limit.
pub const MODEL_MAX_DURATION_KEY: &str = "max_duration";
/// The value that turns an inherited limit off.
pub const DISABLED_LIMIT: &str = "disabled";
