//! The shared name column width of build progress rows.

use crate::build_progress::constants::{MIN_NAME_WIDTH, NAME_PADDING, TREE_CHILD_NAME_INDENT};
use crate::build_progress::models::NameWidthInputs;
use crate::progress::main::format_expectation_name::format_expectation_name;

/// The longest row name plus padding, so tree children still align with top-level statuses.
#[must_use]
pub fn progress_name_width(inputs: &NameWidthInputs) -> usize {
    let top_level = inputs.names.iter().map(|name| name.chars().count());
    let children = inputs.tree_child_names.iter().map(|name| {
        format_expectation_name(name).chars().count() + TREE_CHILD_NAME_INDENT - NAME_PADDING
    });
    let longest: usize = top_level.chain(children).max().unwrap_or(0);
    (longest + NAME_PADDING).max(MIN_NAME_WIDTH)
}
