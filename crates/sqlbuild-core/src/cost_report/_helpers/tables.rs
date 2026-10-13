//! Aligned cost tables: column widths, padding and truncated names.

use crate::cli_text::models::CliStyle;
use crate::cost_report::_helpers::decimal_text::{byte_size, fixed};
use crate::cost_report::constants::{
    COLUMN_GAP, CREDIT_PLACES, ELLIPSIS, NARROW_HEADINGS, NARROW_NAME_LIMIT, NARROW_TERMINAL_WIDTH,
    RESOURCE_NUMERIC_START_COLUMN, SECONDS_PLACES, TOTAL_LABEL, USD_PLACES, WAREHOUSE_NAME_LIMIT,
    WIDE_HEADINGS, WIDE_NAME_LIMIT,
};
use crate::cost_report::models::{CostResource, CostSummary};

fn width(text: &str) -> usize {
    text.chars().count()
}

/// `value.ljust(width)` or `value.rjust(width)`.
pub(crate) fn padded(value: &str, columns: usize, right: bool) -> String {
    let fill: String = " ".repeat(columns.saturating_sub(width(value)));
    if right {
        format!("{fill}{value}")
    } else {
        format!("{value}{fill}")
    }
}

/// `_truncate`: the text, or its prefix and an ellipsis within `limit` characters.
fn truncated(value: &str, limit: usize) -> String {
    if width(value) <= limit {
        return value.to_owned();
    }
    let prefix: String = value
        .chars()
        .take(limit.saturating_sub(ELLIPSIS.len()))
        .collect();
    format!("{prefix}{ELLIPSIS}")
}

/// `_format_usd`.
pub(crate) fn usd(value: &str) -> String {
    format!("${}", fixed(value, USD_PLACES))
}

fn column_width(heading: &str, rows: &[Vec<String>], index: usize) -> usize {
    let mut widest: usize = width(heading);
    for row in rows {
        widest = widest.max(width(&row[index]));
    }
    widest
}

/// `_column_widths`: the widest heading or cell of every column.
pub(crate) fn column_widths(headings: &[&str], rows: &[Vec<String>]) -> Vec<usize> {
    headings
        .iter()
        .enumerate()
        .map(|(index, heading)| column_width(heading, rows, index))
        .collect()
}

fn styled_row(
    style: CliStyle,
    row: &[String],
    (widths, numeric_start): (&[usize], usize),
) -> String {
    let cells: Vec<String> = row
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let cell: String = padded(value, widths[index], index >= numeric_start);
            if index == 0 {
                style.object_name(&cell)
            } else {
                style.value(&cell)
            }
        })
        .collect();
    cells.join(COLUMN_GAP)
}

/// `_format_table_rows`: a styled heading line and one styled line per row.
fn table(
    style: CliStyle,
    headings: &[&str],
    rows: &[Vec<String>],
    numeric_start: usize,
) -> Vec<String> {
    let widths: Vec<usize> = column_widths(headings, rows);
    let heading: Vec<String> = headings
        .iter()
        .enumerate()
        .map(|(index, heading)| padded(heading, widths[index], false))
        .collect();
    let mut lines: Vec<String> = vec![style.label(&heading.join(COLUMN_GAP))];
    lines.extend(
        rows.iter()
            .map(|row| styled_row(style, row, (&widths, numeric_start))),
    );
    lines
}

fn narrow_row(resource: &CostResource) -> Vec<String> {
    vec![
        truncated(&resource.resource_name, NARROW_NAME_LIMIT),
        fixed(&resource.estimated_compute_credits, CREDIT_PLACES),
        usd(&resource.estimated_usd),
    ]
}

fn wide_row(resource: &CostResource) -> Vec<String> {
    vec![
        truncated(&resource.resource_name, WIDE_NAME_LIMIT),
        truncated(&resource.warehouse_name, WAREHOUSE_NAME_LIMIT),
        format!("{}s", fixed(&resource.attributed_seconds, SECONDS_PLACES)),
        byte_size(resource.bytes_scanned),
        fixed(&resource.estimated_compute_credits, CREDIT_PLACES),
        usd(&resource.estimated_usd),
    ]
}

/// `_format_resource_rows`: the narrow or wide resource table with its total.
pub(crate) fn resource_rows(
    style: CliStyle,
    resources: &[CostResource],
    total: &CostSummary,
    terminal_width: usize,
) -> Vec<String> {
    if terminal_width < NARROW_TERMINAL_WIDTH {
        let mut rows: Vec<Vec<String>> = resources.iter().map(narrow_row).collect();
        rows.push(vec![
            TOTAL_LABEL.to_owned(),
            fixed(&total.estimated_compute_credits, CREDIT_PLACES),
            usd(&total.estimated_usd),
        ]);
        return table(
            style,
            &NARROW_HEADINGS,
            &rows,
            RESOURCE_NUMERIC_START_COLUMN - 1,
        );
    }
    let mut rows: Vec<Vec<String>> = resources.iter().map(wide_row).collect();
    rows.push(vec![
        TOTAL_LABEL.to_owned(),
        String::new(),
        format!("{}s", fixed(&total.attributed_seconds, SECONDS_PLACES)),
        byte_size(total.bytes_scanned),
        fixed(&total.estimated_compute_credits, CREDIT_PLACES),
        usd(&total.estimated_usd),
    ]);
    table(style, &WIDE_HEADINGS, &rows, RESOURCE_NUMERIC_START_COLUMN)
}
