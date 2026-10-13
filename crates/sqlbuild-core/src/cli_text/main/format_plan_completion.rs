//! The completion line that closes text plan output.

use crate::cli_text::_helpers::plan_sections::{full_refresh_layout, ready_summary};
use crate::cli_text::constants::{ERROR_SEVERITY_VALUE, PHASE_OK_GLYPH};
use crate::cli_text::models::{CliStyle, PlanTextReport};

/// `✓ Plan complete  <summary>`, warning-styled when the plan has errors.
#[must_use]
pub fn format_plan_completion(report: &PlanTextReport) -> String {
    let style: CliStyle = CliStyle {
        use_color: report.use_color,
    };
    let has_errors: bool = report
        .warnings
        .iter()
        .any(|warning| warning.severity == ERROR_SEVERITY_VALUE);
    let (glyph, label) = if has_errors {
        (
            style.warning(PHASE_OK_GLYPH),
            style.warning_strong("Plan complete with errors"),
        )
    } else {
        (style.success(PHASE_OK_GLYPH), "Plan complete".to_owned())
    };
    let summary: String = ready_summary(report, full_refresh_layout(report));
    format!("{glyph} {label}  {summary}")
}
