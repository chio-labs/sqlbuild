//! Row pieces shared by the persistent build progress lines.

use crate::build_progress::_helpers::text::{counter_width, display_sql, pad};
use crate::build_progress::constants::{LOG_CONTINUATION, LOG_LABEL, TYPE_WIDTH};
use crate::build_progress::models::{LifecycleEventText, ProgressLayout};
use crate::cli_text::main::format_status_cell::format_status_cell;
use crate::cli_text::models::CliStyle;
use crate::text::main::python_splitlines::python_splitlines;

/// The width of the `  N/M  ` prefix every top-level row starts with.
pub(crate) fn prefix_width(layout: ProgressLayout) -> usize {
    2 + counter_width(layout.total) + 2
}

/// The cells of one top-level result row.
pub(crate) struct TopLevelRow<'a> {
    pub(crate) counter: &'a str,
    pub(crate) resource_type: &'a str,
    pub(crate) name: &'a str,
    pub(crate) status: &'a str,
    pub(crate) duration: &'a str,
    pub(crate) detail: &'a str,
}

pub(crate) fn top_level_line(
    row: &TopLevelRow<'_>,
    layout: ProgressLayout,
    style: CliStyle,
) -> String {
    let duration: String = if row.duration.is_empty() {
        String::new()
    } else {
        style.muted(row.duration)
    };
    format!(
        "  {}  {}{} {} {duration}{}\n",
        row.counter,
        style.muted(&pad(row.resource_type, TYPE_WIDTH)),
        pad(row.name, layout.name_width),
        format_status_cell(style, row.status, 6),
        row.detail
    )
}

pub(crate) fn sql_block(sql: &str, style: CliStyle) -> String {
    let mut text: String = "\n".to_owned();
    for line in display_sql(sql).split('\n') {
        text.push_str(&format!("{}\n", style.muted(&format!("    {line}"))));
    }
    text.push('\n');
    text
}

pub(crate) fn log_block(message: &str, style: CliStyle) -> String {
    let lines: Vec<&str> = python_splitlines(message);
    let first: &str = lines.first().copied().unwrap_or("");
    let mut text: String = format!("\n{}{}\n", style.label(LOG_LABEL), style.muted(first));
    for line in lines.iter().skip(1) {
        text.push_str(&format!(
            "{}\n",
            style.muted(&format!("{LOG_CONTINUATION}{line}"))
        ));
    }
    text
}

/// Log blocks, and SQL blocks when verbose, of a lifecycle event list.
pub(crate) fn event_blocks(
    events: &[LifecycleEventText],
    verbose: bool,
    style: CliStyle,
) -> String {
    let mut text: String = String::new();
    for event in events {
        match event {
            LifecycleEventText::Log(message) => text.push_str(&log_block(message, style)),
            LifecycleEventText::Sql(sql) if verbose => text.push_str(&sql_block(sql, style)),
            LifecycleEventText::Sql(_) => {}
        }
    }
    text
}
