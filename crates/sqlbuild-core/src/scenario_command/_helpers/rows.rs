//! Shared pieces of scenario and capture result rows.

use crate::cli_text::main::format_coded_error::format_coded_error;
use crate::cli_text::models::CliStyle;
use crate::scenario_command::constants::{
    BINARY_UNIT_SIZE, CAPTURE_RELATION_KIND_WIDTH, CAPTURE_RELATION_NAME_WIDTH, FAIL_STATUS,
    PASS_STATUS, SCENARIO_NAME_WIDTH,
};
use crate::scenario_command::models::{CaptureRelationRow, CodedText};
use crate::text::main::python_splitlines::python_splitlines;

/// `render_result_error`: the coded error when it has a code, else its message.
pub(crate) fn result_error(error: &CodedText, style: CliStyle) -> String {
    match &error.code {
        Some(code) => {
            format_coded_error((code, &error.message, error.help.as_deref()), true, style)
        }
        None => error.message.clone(),
    }
}

/// Each line of a rendered result error, indented by four spaces.
pub(crate) fn indented_error_lines(error: &CodedText, style: CliStyle) -> String {
    python_splitlines(&result_error(error, style))
        .into_iter()
        .map(|line| format!("    {line}\n"))
        .collect()
}

/// `row` for one, `rows` otherwise.
pub(crate) fn rows_label(count: i64) -> &'static str {
    if count == 1 { "row" } else { "rows" }
}

/// The result row heading: the padded name, the styled status and its detail.
pub(crate) fn heading(name: &str, status: &str, detail: &str) -> String {
    format!("{name:<SCENARIO_NAME_WIDTH$} {status}{detail}\n")
}

/// A snapshot size in bytes, KB or MB with binary units.
pub(crate) fn snapshot_size(byte_count: i64) -> String {
    let bytes: f64 = byte_count as f64;
    if bytes < BINARY_UNIT_SIZE {
        return format!("{byte_count} B");
    }
    let kibibytes: f64 = bytes / BINARY_UNIT_SIZE;
    if kibibytes < BINARY_UNIT_SIZE {
        return format!("{kibibytes:.1} KB");
    }
    format!("{:.1} MB", kibibytes / BINARY_UNIT_SIZE)
}

/// `  <n> relation(s), <n> row(s)`: passed relations and every captured row.
pub(crate) fn capture_detail(relations: &[CaptureRelationRow]) -> String {
    let relation_count: usize = relations.iter().filter(|relation| relation.passed).count();
    let row_count: i64 = relations.iter().map(|relation| relation.row_count).sum();
    let relation_label: &str = if relation_count == 1 {
        "relation"
    } else {
        "relations"
    };
    format!(
        "  {relation_count} {relation_label}, {row_count} {}",
        rows_label(row_count)
    )
}

/// One captured relation row under its scenario.
pub(crate) fn capture_relation_rows(relations: &[CaptureRelationRow], style: CliStyle) -> String {
    relations
        .iter()
        .map(|relation| {
            let status: String = style.status(if relation.passed {
                PASS_STATUS
            } else {
                FAIL_STATUS
            });
            format!(
                "    {:<CAPTURE_RELATION_KIND_WIDTH$} {:<CAPTURE_RELATION_NAME_WIDTH$} {status}  {} {}, {}\n",
                relation.kind,
                relation.logical_name,
                relation.row_count,
                rows_label(relation.row_count),
                snapshot_size(relation.byte_count)
            )
        })
        .collect()
}

/// The snapshot manifest line.
pub(crate) fn snapshot_line(path: &str) -> String {
    format!("    {:<CAPTURE_RELATION_KIND_WIDTH$} {path}\n", "snapshot")
}
