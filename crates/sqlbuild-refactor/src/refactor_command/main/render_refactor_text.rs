//! The human output of `sqb rename` and `sqb mv`.

use sqlbuild_core::cli_text::models::CliStyle;

use crate::refactor_command::_helpers::output_text::{
    batch_lines, change_lines, diagnostic_lines, heading, layer_move_lines, location_lines,
    migration_lines, refactor_target, status_line, verb,
};
use crate::refactor_command::models::{LayerMove, RefactorDiagnostic, RefactorStatus};
use crate::refactoring::models::{ManualLocation, RefactorPlan};

/// The edit tree, manual locations, compile errors, and one terminal status line.
#[must_use]
pub fn render_refactor_text(
    plan: &RefactorPlan,
    (status, diagnostics): (RefactorStatus, &[RefactorDiagnostic]),
    layer_move: Option<&LayerMove>,
    style: CliStyle,
) -> String {
    let mut lines: Vec<String> = vec![style.title(&heading(plan))];
    lines.extend(batch_lines(style, plan));
    let blocked: bool = status == RefactorStatus::Refused;
    if !blocked || (plan.blocking.is_empty() && plan.manual.is_empty()) {
        lines.extend(change_lines(style, &plan.changes));
    }
    if !plan.migrations.is_empty() && !blocked {
        lines.push(style.section("Migrations"));
        lines.extend(migration_lines(style, &plan.migrations));
    }
    if !plan.notes.is_empty() && !blocked {
        lines.push(style.section("Notes"));
        let notes: Vec<&ManualLocation> = plan.notes.iter().collect();
        lines.extend(location_lines(style, &notes));
    }
    if blocked {
        lines.push(style.error_strong(&format!(
            "Cannot {} {} automatically",
            verb(plan),
            refactor_target(plan)
        )));
        let locations: Vec<&ManualLocation> = plan.blocking.iter().chain(&plan.manual).collect();
        lines.extend(location_lines(style, &locations));
        if let Some(help) = &plan.help
            && !plan.manual.is_empty()
        {
            lines.push(help.clone());
        }
    }
    if !diagnostics.is_empty() {
        lines.push(style.error_strong("Compile errors in the edited project"));
        lines.extend(diagnostic_lines(style, diagnostics));
    }
    if let Some(layer_move) = layer_move {
        lines.extend(layer_move_lines(style, layer_move));
    }
    lines.push(status_line(style, plan, status));
    format!("{}\n", lines.join("\n"))
}
