//! `rebound_scope_usages`: which used declarations a resource file would lose or rebind if moved.

use crate::scope_report::_helpers::moves::rebound_usages;
use crate::scope_report::models::{ReportFailure, ReportSource};

/// Used scoped declarations that resolve differently from `destination`; `None` if it is invalid.
pub fn rebound_scope_usages(
    source: ReportSource<'_>,
    paths: (&str, &str),
) -> Result<Option<Vec<String>>, ReportFailure> {
    rebound_usages(source, paths)
}
