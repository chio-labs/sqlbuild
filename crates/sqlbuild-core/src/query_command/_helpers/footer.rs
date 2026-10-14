//! The row count and truncation lines under long and table output.

use crate::query_command::models::QueryDisplay;

/// A blank line, `<n> row(s)`, and the truncation hint when the limit cut rows off.
pub(crate) fn footer(display: &QueryDisplay) -> Vec<String> {
    let count: usize = display.rows.len();
    let mut lines: Vec<String> = vec![
        String::new(),
        format!("{count} {}", if count == 1 { "row" } else { "rows" }),
    ];
    if display.truncated {
        lines.push(display.limit.map_or_else(String::new, |limit| {
            format!(
                "Showing {limit} rows. Use --limit to show more or --no-limit to disable the limit."
            )
        }));
    }
    lines
}
