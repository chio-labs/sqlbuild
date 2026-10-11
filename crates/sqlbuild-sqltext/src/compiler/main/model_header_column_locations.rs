//! Authored locations of the column names a MODEL header declares.

use crate::compiler::models::TextLocation;

/// Python's `header_column_locations` for `header` authored at code point `header_start`.
pub fn model_header_column_locations(
    contents: &str,
    header: &str,
    header_start: usize,
) -> Result<Vec<(String, TextLocation)>, String> {
    crate::compiler::_helpers::model_headers::locations::header_column_locations(
        contents,
        header,
        header_start,
    )
}
