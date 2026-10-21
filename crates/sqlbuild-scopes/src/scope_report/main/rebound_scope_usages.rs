//! `rebound_scope_usages`: which used declarations a resource file would lose or rebind if moved.

use crate::scope_report::_helpers::moves::rebound_usages;
use crate::scope_report::models::{ReportFailure, ReportSource};

/// Qualified identities of the scoped macros, enums and constants the resources at `path` use
/// that resolve differently from `destination`, or `None` when `destination` cannot hold them.
pub fn rebound_scope_usages(
    source: ReportSource<'_>,
    paths: (&str, &str),
) -> Result<Option<Vec<String>>, ReportFailure> {
    rebound_usages(source, paths)
}
