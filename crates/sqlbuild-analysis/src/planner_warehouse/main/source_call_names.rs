//! Source names called as `__source("name")` in SQL text.

use crate::planner_warehouse::constants::SOURCE_CALL_OPEN;

/// Every non-overlapping `__source("name")` name, in text order.
pub fn source_call_names(sql: &str) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    let mut position = 0;
    while let Some(found) = sql[position..].find(SOURCE_CALL_OPEN) {
        let start = position + found + SOURCE_CALL_OPEN.len();
        let rest = &sql[start..];
        match rest.find('"') {
            Some(end) if end > 0 && rest[end + 1..].starts_with(')') => {
                names.push(rest[..end].to_owned());
                position = start + end + 2;
            }
            _ => position += found + 1,
        }
    }
    names
}
