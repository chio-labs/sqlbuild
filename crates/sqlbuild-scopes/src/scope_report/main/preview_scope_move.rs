//! `preview_scope_move`: how a resource's visible declarations change if it moves.

use crate::scope_report::_helpers::moves::move_preview;
use crate::scope_report::models::{
    DiagnosticFacts, MovePreview, MoveRequest, ReportFailure, ReportSource,
};

/// The move preview of `request`, or why it cannot be previewed.
pub fn preview_scope_move(
    source: ReportSource<'_>,
    request: &MoveRequest,
) -> Result<(Option<MovePreview>, Vec<DiagnosticFacts>), ReportFailure> {
    move_preview(source, request)
}
