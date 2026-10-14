//! Fixture alignment phases.

use crate::planner_fixtures::models::AlignmentInput;

pub(crate) fn supplied_in_schema_order(input: &AlignmentInput<'_>) -> bool {
    input
        .supplied
        .iter()
        .map(|column| &column.folded_name)
        .eq(input
            .metadata
            .iter()
            .take(input.supplied.len())
            .map(|column| &column.folded_name))
}
