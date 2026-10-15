//! Narrow a sink's minimum severity by an optional configured minimum.

use crate::event_export::models::ExportSeverity;

/// The stricter of a required minimum and an optional one.
#[must_use]
pub fn stricter_severity(first: ExportSeverity, second: Option<ExportSeverity>) -> ExportSeverity {
    match second {
        Some(second) if second > first => second,
        _ => first,
    }
}
