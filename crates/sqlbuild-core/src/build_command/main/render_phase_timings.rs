//! Verbose build phase timings.

use crate::build_command::constants::PHASE_LABEL_WIDTH;
use crate::build_command::models::PhaseTimings;
use crate::cli_text::models::{CliDocument, CliStyle};

/// A blank line, the `Phase timings` header and one row per measured phase.
#[must_use]
pub fn render_phase_timings(timings: &PhaseTimings, style: CliStyle) -> String {
    let phases: [(&str, Option<f64>); 7] = [
        ("compile", timings.compile_seconds),
        ("planning", timings.planning_seconds),
        (
            "connection preparation",
            timings.connection_preparation_seconds,
        ),
        ("schema preparation", timings.schema_preparation_seconds),
        ("execution", timings.execution_seconds),
        ("cost collection", timings.cost_collection_seconds),
        ("total", timings.total_seconds),
    ];
    let mut rows: Vec<(String, String)> = Vec::new();
    for (label, seconds) in phases {
        if let Some(seconds) = seconds {
            rows.push((label.to_owned(), format!("{seconds:.2}s")));
        }
    }
    let mut document: CliDocument = CliDocument::new(style);
    document.lines.push(String::new());
    document.header("Phase timings", None);
    document.fields(&rows, Some(PHASE_LABEL_WIDTH));
    document.render(true)
}
