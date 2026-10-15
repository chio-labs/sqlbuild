//! The unmerged MIN/MAX statement of one physical cursor read.

use crate::planner_warehouse::models::PhysicalCursorQuery;

/// Select the requested bounds of the cursor column as text.
pub fn cursor_query_sql(query: &PhysicalCursorQuery) -> String {
    let mut parts: Vec<String> = Vec::new();
    if !query.min_tags.is_empty() {
        parts.push(format!(
            "CAST(MIN({}) AS VARCHAR) AS _min",
            query.cursor_column
        ));
    }
    if !query.max_tags.is_empty() {
        parts.push(format!(
            "CAST(MAX({}) AS VARCHAR) AS _max",
            query.cursor_column
        ));
    }
    format!("SELECT {} FROM {}", parts.join(", "), query.relation)
}
