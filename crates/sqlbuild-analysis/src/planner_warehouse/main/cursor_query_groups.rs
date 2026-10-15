//! Group logical cursor bounds by the physical relation column that answers them.

use crate::planner_warehouse::constants::TIMESTAMP_CURSOR_TYPE;
use crate::planner_warehouse::models::{CursorTagRequest, PhysicalCursorQuery};

/// Merge requests into one query per relation, column and type, in first-request order.
pub fn cursor_query_groups(requests: &[CursorTagRequest]) -> Vec<PhysicalCursorQuery> {
    let mut groups: Vec<PhysicalCursorQuery> = Vec::new();
    for request in requests {
        let cursor_type = request
            .cursor_type
            .clone()
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| TIMESTAMP_CURSOR_TYPE.to_owned());
        let position = groups.iter().position(|group| {
            group.relation == request.relation
                && group.cursor_column == request.cursor_column
                && group.cursor_type == cursor_type
        });
        let index = position.unwrap_or_else(|| {
            groups.push(PhysicalCursorQuery {
                relation: request.relation.clone(),
                cursor_column: request.cursor_column.clone(),
                cursor_type,
                min_tags: Vec::new(),
                max_tags: Vec::new(),
            });
            groups.len() - 1
        });
        let group = &mut groups[index];
        if let Some(min_tag) = &request.min_tag
            && !group.min_tags.contains(min_tag)
        {
            group.min_tags.push(min_tag.clone());
        }
        if !group.max_tags.contains(&request.max_tag) {
            group.max_tags.push(request.max_tag.clone());
        }
    }
    groups
}
