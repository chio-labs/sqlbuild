//! Whether a diff compares raw queries instead of project models.

use crate::diff_report::models::DiffRequestFacts;

/// Any raw-query input was supplied.
#[must_use]
pub fn is_query_diff_request(request: &DiffRequestFacts) -> bool {
    request.left_query || request.left_query_file || request.right_query || request.right_query_file
}
