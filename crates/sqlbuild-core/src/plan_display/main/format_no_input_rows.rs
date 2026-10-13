//! The note for a cursor window whose inputs have no rows.

/// `no input rows (<names>)`.
#[must_use]
pub fn format_no_input_rows(input_names: &[String]) -> String {
    format!("no input rows ({})", input_names.join(", "))
}
