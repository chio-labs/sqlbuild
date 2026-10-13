//! Whether a scope result makes `sqb scope` exit with failure.

use crate::scope_report::models::ScopeResult;
use crate::scope_text::_helpers::layout::has_error;

/// A result fails when it is partial or carries an error diagnostic.
#[must_use]
pub fn scope_result_failed(result: &ScopeResult) -> bool {
    let (complete, diagnostics) = match result {
        ScopeResult::Report(report) => (report.complete, &report.diagnostics),
        ScopeResult::Browse(browse) => (browse.complete, &browse.diagnostics),
        ScopeResult::List(list) => (list.section.complete, &list.diagnostics),
    };
    !complete || has_error(diagnostics)
}
