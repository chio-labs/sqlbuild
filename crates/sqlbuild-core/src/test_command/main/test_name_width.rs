//! One shared width for test rows and their nested expectation rows.

use crate::cli_text::main::resolve_name_column_width::resolve_name_column_width;
use crate::test_command::constants::{CHILD_NAME_INDENT, NAME_MIN_WIDTH};

/// The test label column width, widened for the longest indented child name.
#[must_use]
pub fn test_name_width(labels: &[String], child_names: &[String]) -> usize {
    let child: usize = child_names
        .iter()
        .map(|name| name.chars().count())
        .max()
        .unwrap_or(0);
    resolve_name_column_width(labels, NAME_MIN_WIDTH).max(child + CHILD_NAME_INDENT)
}
