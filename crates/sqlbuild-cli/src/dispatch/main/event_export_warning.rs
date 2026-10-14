//! The stderr warning for lifecycle events dropped or failed at command exit.

use crate::dispatch::constants::SHUTDOWN_TIMEOUT_SETTING;
use crate::dispatch::models::{ExportSummary, ExporterLoss};

/// One warning line when lifecycle events were dropped or failed, else `None`.
#[must_use]
pub fn event_export_warning(summary: &ExportSummary, command_succeeded: bool) -> Option<String> {
    if summary.dropped == 0 && summary.failed == 0 {
        return None;
    }
    let affected: Vec<&ExporterLoss> = summary
        .per_exporter
        .iter()
        .filter(|exporter| exporter.dropped > 0 || exporter.failed > 0)
        .collect();
    let names: String = affected
        .iter()
        .map(|exporter| format!("'{}'", exporter.exporter_name))
        .collect::<Vec<String>>()
        .join(", ");
    let sink_label: &str = if affected.len() == 1 { "sink" } else { "sinks" };
    let unit: &str = if summary.per_exporter.len() == 1 {
        "events"
    } else {
        "event deliveries"
    };
    let prefix: &str = if command_succeeded {
        "Warning: command completed successfully, but lifecycle event export was incomplete"
    } else {
        "Warning: lifecycle event export was incomplete"
    };
    Some(format!(
        "{prefix}: {} of {} {unit} dropped, {} failed ({sink_label} {names}). \
         Increase {SHUTDOWN_TIMEOUT_SETTING} or check sink health.",
        summary.dropped, summary.accepted, summary.failed
    ))
}
