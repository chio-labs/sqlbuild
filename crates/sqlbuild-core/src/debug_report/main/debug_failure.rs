//! `debug_failure`: the structured cause of a failed `sqb debug`, for the invocation record.

use crate::debug_report::constants::{
    CONNECTION_FAILED_CODE, CONNECTION_TEST_LABEL, DEBUG_CHECK_FAILED_CODE, QUERY_FAILED_CODE,
    QUERY_TEST_LABEL,
};
use crate::debug_report::models::{DebugFailure, DebugReport, DebugStatus};

/// The first failed check: its error type, code and message; `None` when every check passed.
#[must_use]
pub fn debug_failure(report: &DebugReport) -> Option<DebugFailure> {
    let line = [
        &report.connection,
        &report.configuration,
        &report.runtime,
        &report.providers,
    ]
    .into_iter()
    .flatten()
    .find(|line| line.status == Some(DebugStatus::Error))?;
    let detail: String = line
        .status_message
        .clone()
        .filter(|message| !message.is_empty())
        .unwrap_or_else(|| line.message.clone());
    let (error_type, error_code) = match line.label.as_str() {
        CONNECTION_TEST_LABEL => ("ConnectionError", CONNECTION_FAILED_CODE),
        QUERY_TEST_LABEL => ("QueryError", QUERY_FAILED_CODE),
        _ => ("ConfigurationError", DEBUG_CHECK_FAILED_CODE),
    };
    Some(DebugFailure {
        error_type: error_type.to_owned(),
        error_code: error_code.to_owned(),
        message: format!("{}: {detail}", line.label),
    })
}
