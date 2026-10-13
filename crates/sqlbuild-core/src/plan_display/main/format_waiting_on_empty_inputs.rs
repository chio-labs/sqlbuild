//! The note for a cursor window waiting on empty inputs while others have rows.

/// `waiting on empty input(s) <names>; other inputs have new rows`.
#[must_use]
pub fn format_waiting_on_empty_inputs(input_names: &[String]) -> String {
    let noun: &str = if input_names.len() == 1 {
        "input"
    } else {
        "inputs"
    };
    format!(
        "waiting on empty {noun} {}; other inputs have new rows",
        input_names.join(", ")
    )
}
