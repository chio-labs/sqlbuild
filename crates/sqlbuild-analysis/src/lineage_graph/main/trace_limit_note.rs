//! The note shown when a column trace is truncated.

/// The note's lines, before styling, when `total` columns exceed the `limit` shown.
pub fn trace_limit_note(total: i64, limit: i64) -> Vec<String> {
    if total <= limit {
        return Vec::new();
    }
    vec![
        format!("Showing {limit} of {total} columns."),
        "Use --depth 1 to show direct column dependencies only.".to_owned(),
        "Use --format json for the full trace.".to_owned(),
    ]
}
