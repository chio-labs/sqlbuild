//! Compare a catalogued severity with a sink's minimum.

use crate::event_export::models::ExportSeverity;

/// Whether `severity` meets the configured `minimum`.
#[must_use]
pub fn severity_at_least(severity: ExportSeverity, minimum: ExportSeverity) -> bool {
    severity >= minimum
}
