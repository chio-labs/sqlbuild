//! Reject contradictory or out-of-range `sqb diff` flags before any discovery.

use crate::diff_report::_helpers::request_rules::{
    common_violation, model_violation, query_violation, user_error,
};
use crate::diff_report::errors::DiffUserError;
use crate::diff_report::main::is_query_diff_request::is_query_diff_request;
use crate::diff_report::models::DiffRequestFacts;

/// The first violated rule, checked in the order users see them reported.
pub fn validate_diff_request(request: &DiffRequestFacts) -> Result<(), DiffUserError> {
    let violation: Option<(&str, &str)> = common_violation(request).or_else(|| {
        if is_query_diff_request(request) {
            query_violation(request)
        } else {
            model_violation(request)
        }
    });
    violation.map_or(Ok(()), |(message, code)| Err(user_error(message, code)))
}
