use crate::compiled_project::models::HeaderColumnShape;

/// Whether any header column is typed as one of the visible enums.
pub fn enum_typed_columns(columns: &[HeaderColumnShape], enum_names: &[String]) -> bool {
    crate::compiled_project::_helpers::plain::enum_typed_columns(columns, enum_names)
}
