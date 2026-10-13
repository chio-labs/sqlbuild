//! The text plan, grouped by reason with inline detail.

use crate::cli_text::_helpers::bounded_sections::strip_ansi;
use crate::cli_text::_helpers::plan_document::{full_refresh_lines, incremental_lines};
use crate::cli_text::_helpers::plan_sections::{active_models, full_refresh_layout};
use crate::cli_text::models::{ModelPlanText, PlanTextReport};

/// The plan as `format_plan` printed it, without the completion line.
#[must_use]
pub fn format_plan_text(report: &PlanTextReport) -> String {
    let active: Vec<&ModelPlanText> = active_models(report);
    let lines: Vec<String> = if full_refresh_layout(report) {
        full_refresh_lines(report, &active)
    } else {
        incremental_lines(report, &active)
    };
    let text: String = lines.join("\n");
    if report.use_color {
        return text;
    }
    strip_ansi(&text)
}
