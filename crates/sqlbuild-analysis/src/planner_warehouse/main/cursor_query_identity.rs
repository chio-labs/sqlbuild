//! The progress label of one physical cursor read.

use crate::planner_warehouse::main::cursor_bounds::cursor_bounds;
use crate::planner_warehouse::models::PhysicalCursorQuery;

/// `(index/total): relation.column [bounds]`.
pub fn cursor_query_identity(
    query: &PhysicalCursorQuery,
    (index, total): (usize, usize),
) -> String {
    format!(
        "({index}/{total}): {}.{} [{}]",
        query.relation,
        query.cursor_column,
        cursor_bounds(query)
    )
}
