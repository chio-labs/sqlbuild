//! The human text of one `sqb scope` result.

use sqlbuild_core::cli_text::models::CliStyle;

use crate::scope_report::models::ScopeResult;
use crate::scope_text::_helpers::results::{browse_text, list_text, report_text};
use crate::scope_text::models::ScopeTextRequest;

/// Render a compiler-owned scope result without deriving scope facts.
#[must_use]
pub fn render_scope_text(
    result: &ScopeResult,
    request: &ScopeTextRequest,
    style: CliStyle,
) -> String {
    match result {
        ScopeResult::Report(report) => report_text((style, request), report),
        ScopeResult::Browse(browse) => browse_text((style, request), browse),
        ScopeResult::List(list) => list_text((style, request), list),
    }
}
