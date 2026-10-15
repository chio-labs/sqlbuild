//! Which bounds one physical cursor read selects.

use crate::planner_warehouse::models::PhysicalCursorQuery;

/// `min`, `max` or `min,max`, as shown in progress and debug events.
pub fn cursor_bounds(query: &PhysicalCursorQuery) -> String {
    match (query.min_tags.is_empty(), query.max_tags.is_empty()) {
        (false, false) => "min,max".to_owned(),
        (false, true) => "min".to_owned(),
        (true, false) => "max".to_owned(),
        (true, true) => String::new(),
    }
}
