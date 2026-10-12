use crate::compiled_project::models::TextPosition;

/// Where the first whole-word `sql_analysis` or `sql_validation` at or after character `start` is.
pub fn opt_out_position(text: &str, start: usize) -> TextPosition {
    crate::compiled_project::_helpers::sources::opt_out_position(text, start)
}
