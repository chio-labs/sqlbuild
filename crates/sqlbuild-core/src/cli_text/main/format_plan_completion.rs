//! The completion line that closes text plan output.

use crate::cli_text::_helpers::plan_sections::{full_refresh_layout, ready_summary};
use crate::cli_text::constants::{ERROR_SEVERITY_VALUE, PHASE_FAIL_GLYPH, PHASE_OK_GLYPH};
use crate::cli_text::models::{CliStyle, PlanTextReport};

/// `✓ Plan complete  <summary>`, or `✗ Plan failed` when the plan has errors a build refuses.
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
            style.error(PHASE_FAIL_GLYPH),
            style.error_strong("Plan failed with errors"),
        )
    } else {
        (style.success(PHASE_OK_GLYPH), "Plan complete".to_owned())
    };
    let summary: String = ready_summary(report, full_refresh_layout(report));
    format!("{glyph} {label}  {summary}")
}
