//! The dim connector of one tree row.

use crate::cli_text::_helpers::layout::tree_connector;
use crate::cli_text::models::CliStyle;

/// `tree_connector`: a dim branch, or the last branch of a group.
#[must_use]
pub fn format_tree_connector(style: CliStyle, last: bool) -> String {
    tree_connector(style, last)
}
