//! `query_scope_report`: what an existing target or prospective path can see, page by page.

use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::report::{Resolved, record_report, resolve, unresolved_report};
use crate::scope_report::models::{ReportFailure, ReportRequest, ReportSource, ScopeReport};

/// The report of `request` over one lookup, or the path or identity error Python raises.
pub fn build_scope_report(
    source: ReportSource<'_>,
    request: &ReportRequest,
) -> Result<ScopeReport, ReportFailure> {
    let context: Context<'_> = Context::new(source);
    match resolve(&context, request)? {
        Resolved::Record(resource, record, raised) => {
            record_report(&context, &request.filters, (resource, record, raised))
        }
        Resolved::Done(resource, explanation, raised) => Ok(unresolved_report(
            &context,
            &request.filters,
            (resource, explanation, raised),
        )),
    }
}
