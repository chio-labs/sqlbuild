//! The row count line under every text layout.

use crate::query_command::constants::MANY_ROWS;
use crate::query_command::models::QueryDisplay;

/// A blank line and the row count: when the limit cut rows off, the limit and how to change it; above [`MANY_ROWS`], a hint to aggregate or limit the query.
pub(crate) fn footer(display: &QueryDisplay) -> Vec<String> {
    let count: usize = display.rows.len();
    let noun: &str = if count == 1 { "row" } else { "rows" };
    let line: String = match display.limit.filter(|_| display.truncated) {
        Some(limit) => format!("{count} {noun} shown (limit {limit}; use --limit or --no-limit)"),
        None if count > MANY_ROWS => {
            format!("{count} {noun}; to read fewer, aggregate with GROUP BY or add a LIMIT")
        }
        None => format!("{count} {noun}"),
    };
    vec![String::new(), line]
}
