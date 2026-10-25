//! The unmerged MIN/MAX statement of one physical cursor read.

use crate::planner_warehouse::models::PhysicalCursorQuery;

/// Select the requested bounds of the cursor column as text, each through `as_text`.
pub fn cursor_query_sql(query: &PhysicalCursorQuery, as_text: &dyn Fn(&str) -> String) -> String {
    let mut parts: Vec<String> = Vec::new();
    if !query.min_tags.is_empty() {
        parts.push(format!(
            "{} AS _min",
            as_text(&format!("MIN({})", query.cursor_column))
        ));
    }
    if !query.max_tags.is_empty() {
        parts.push(format!(
            "{} AS _max",
            as_text(&format!("MAX({})", query.cursor_column))
        ));
    }
    format!("SELECT {} FROM {}", parts.join(", "), query.relation)
}
