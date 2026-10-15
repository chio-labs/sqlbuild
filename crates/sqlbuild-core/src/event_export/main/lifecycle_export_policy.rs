//! Destination-neutral export dimensions of one catalogued lifecycle event type.

use crate::event_export::constants::{
    FAILED_EVENT_PRIORITY, FAILED_EVENT_SUFFIX, PROGRESS_EVENT_PRIORITY, RETRY_EVENT_KIND,
    RETRY_EVENT_PRIORITY, RETRY_EVENT_TYPE, TERMINAL_EVENT_PRIORITY,
};
use crate::event_export::models::{ExportPolicy, ExportSeverity};

/// The kind, severity and queue priority of `event_type`, whose catalogue entry is `terminal`.
#[must_use]
pub fn lifecycle_export_policy(event_type: &str, terminal: bool) -> ExportPolicy {
    if event_type == RETRY_EVENT_TYPE {
        return ExportPolicy {
            kind: RETRY_EVENT_KIND.to_owned(),
            severity: ExportSeverity::Warning,
            priority: RETRY_EVENT_PRIORITY,
        };
    }
    let kind: &str = event_type.split('_').next().unwrap_or(event_type);
    let failed: bool = event_type.ends_with(FAILED_EVENT_SUFFIX);
    let (severity, priority) = if failed {
        (ExportSeverity::Error, FAILED_EVENT_PRIORITY)
    } else if terminal {
        (ExportSeverity::Info, TERMINAL_EVENT_PRIORITY)
    } else {
        (ExportSeverity::Debug, PROGRESS_EVENT_PRIORITY)
    };
    ExportPolicy {
        kind: kind.to_owned(),
        severity,
        priority,
    }
}
