//! `browse_scope_folders`: the direct child declaration-definition folders of one folder.

use crate::scope_report::_helpers::folders::browsing;
use crate::scope_report::models::{BrowseResult, FolderRequest, ReportSource};

/// The browse result of `request` over one lookup.
#[must_use]
pub fn browse_scope_folders(source: ReportSource<'_>, request: &FolderRequest) -> BrowseResult {
    browsing(source, request)
}
