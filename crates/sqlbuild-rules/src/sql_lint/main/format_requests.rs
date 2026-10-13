//! Typed, in-process batch formatting of neutralized SQL bodies.

use crate::sql_lint::models::{FormatRequest, FormatResponse};

/// Format every request in parallel and return the responses in request order.
pub(crate) fn format_requests(requests: Vec<FormatRequest>) -> Vec<FormatResponse> {
    crate::sql_lint::_helpers::formatter::format_requests(requests)
}
