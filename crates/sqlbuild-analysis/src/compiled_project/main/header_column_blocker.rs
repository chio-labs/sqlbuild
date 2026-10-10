use crate::compiled_project::models::{HeaderColumnShape, PlainModelBlocker};

/// Why parsed header columns still need the attachment, or `None` when the loop attaches them.
pub fn header_column_blocker(
    columns: &[HeaderColumnShape],
    enum_names: &[String],
) -> Option<PlainModelBlocker> {
    crate::compiled_project::_helpers::plain::header_column_blocker(columns, enum_names)
}
