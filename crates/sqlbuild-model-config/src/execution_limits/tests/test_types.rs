use crate::execution_limits::models::ExecutionLimit;

/// One limit text and the limit it parses to, if any.
pub(super) struct ParseExecutionLimitTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_limit: Option<ExecutionLimit>,
}
