//! `list_scope_declarations`: declarations recursively beneath one definition folder.

use crate::scope_report::_helpers::folders::listing;
use crate::scope_report::models::{FolderRequest, ListResult, ReportFailure, ReportSource};

/// The list result of `request`, or the path error Python raises.
pub fn list_scope_declarations(
    source: ReportSource<'_>,
    request: &FolderRequest,
) -> Result<ListResult, ReportFailure> {
    listing(source, request)
}
