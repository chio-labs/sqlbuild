//! Query rows as one expanded record per row.

use crate::query_command::_helpers::footer::footer;
use crate::query_command::constants::RECORD_RULE_WIDTH;
use crate::query_command::models::QueryDisplay;

/// `-[ RECORD n ]---+` then `column | value` lines per row, then the row count.
#[must_use]
pub(crate) fn long_text(display: &QueryDisplay) -> String {
    let width: usize = display
        .columns
        .iter()
        .map(|column| column.chars().count())
        .max()
        .unwrap_or(0);
    let mut lines: Vec<String> = Vec::new();
    for (index, row) in display.rows.iter().enumerate() {
        if !lines.is_empty() {
            lines.push(String::new());
        }
        let header: String = format!("-[ RECORD {} ]", index + 1);
        let rule: usize = RECORD_RULE_WIDTH.saturating_sub(header.chars().count());
        lines.push(format!("{header}{}+", "-".repeat(rule)));
        for (column, value) in display.columns.iter().zip(row) {
            lines.push(format!("{column:<width$} | {value}"));
        }
    }
    lines.extend(footer(display));
    format!("{}\n", lines.join("\n"))
}
