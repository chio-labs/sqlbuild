//! Table-type and retention work that runs before model builds.

use crate::cli_text::main::format_overflow_line::format_overflow_line;
use crate::cli_text::models::PreBuildWorkText;

fn days(value: Option<i64>) -> String {
    value.map_or_else(|| "missing".to_owned(), |days| format!("{days}d"))
}

/// Append table-type conversions, with an overflow hint, and every retention change.
#[must_use]
pub fn format_pre_build_work(mut lines: Vec<String>, work: &PreBuildWorkText) -> Vec<String> {
    if !work.table_types.is_empty() {
        lines.push("Table type conversions".to_owned());
        let visible = work
            .display
            .max_entries
            .map_or(work.table_types.len(), |limit| {
                limit.min(work.table_types.len())
            });
        for entry in &work.table_types[..visible] {
            lines.push(format!(
                "  {} desired={} actual={} source={}",
                entry.model_name,
                entry.desired_type,
                entry.actual_type.as_deref().unwrap_or("unknown"),
                entry.source
            ));
            if let Some(warning) = &entry.irreversible_warning {
                lines.push(format!("    WARNING: {warning}"));
            }
        }
        let hidden = i64::try_from(work.table_types.len() - visible).unwrap_or(i64::MAX);
        if let Some(line) = format_overflow_line(hidden, "  ", &work.display.overflow_flag) {
            lines.push(line);
        }
    }
    if !work.retention.is_empty() {
        lines.push("Retention".to_owned());
    }
    for entry in &work.retention {
        lines.push(format!(
            "  {} desired={}d actual={} effective={} source={} direction={} phase={}",
            entry.scope,
            entry.desired_days,
            days(entry.actual_days),
            days(entry.effective_days),
            entry.source,
            entry.direction,
            entry.phase
        ));
        if let Some(warning) = &entry.irreversible_warning {
            lines.push(format!("    WARNING: {warning}"));
        }
    }
    lines
}
