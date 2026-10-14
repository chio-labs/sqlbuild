//! Query rows as an aligned table.

use crate::query_command::_helpers::footer::footer;
use crate::query_command::constants::TABLE_SEPARATOR;
use crate::query_command::models::QueryDisplay;
use crate::text::main::python_isspace::python_isspace;

fn padded(value: &str, width: usize) -> String {
    format!("{value:<width$}")
}

/// A header, a dashed rule, one right-trimmed line per row, then the row count.
#[must_use]
pub fn render_query_table(display: &QueryDisplay) -> String {
    let mut widths: Vec<usize> = display
        .columns
        .iter()
        .map(|column| column.chars().count())
        .collect();
    for row in &display.rows {
        for (index, value) in row.iter().enumerate() {
            if let Some(width) = widths.get_mut(index) {
                *width = (*width).max(value.chars().count());
            }
        }
    }
    let width_at = |index: usize| widths.get(index).copied().unwrap_or(0);
    let mut lines: Vec<String> = vec![
        display
            .columns
            .iter()
            .enumerate()
            .map(|(index, column)| padded(column, width_at(index)))
            .collect::<Vec<String>>()
            .join(TABLE_SEPARATOR),
        widths
            .iter()
            .map(|width| "-".repeat(*width))
            .collect::<Vec<String>>()
            .join(TABLE_SEPARATOR),
    ];
    for row in &display.rows {
        let line: String = row
            .iter()
            .enumerate()
            .map(|(index, value)| padded(value, width_at(index)))
            .collect::<Vec<String>>()
            .join(TABLE_SEPARATOR);
        lines.push(line.trim_end_matches(python_isspace).to_owned());
    }
    lines.extend(footer(display));
    format!("{}\n", lines.join("\n"))
}
