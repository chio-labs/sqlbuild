//! Whether an authored cursor input column is exposed by the input it names.

use crate::planner_strategy::constants::CURSOR_INPUT_COLUMN_ERROR_CODE;
use crate::planner_strategy::models::{CursorInputColumnCheck, CursorInputColumnOwner};

/// The planner error message and code when the column is missing from the known columns, matched case-insensitively.
pub fn cursor_input_column_failure(
    check: &CursorInputColumnCheck,
) -> Option<(String, &'static str)> {
    let column: String = check.column.to_lowercase();
    if check
        .known_columns
        .iter()
        .any(|known| known.to_lowercase() == column)
    {
        return None;
    }
    let (kind, exposer, label) = match check.owner {
        CursorInputColumnOwner::ModelContract => {
            ("model", "that model contract", "Known output columns")
        }
        CursorInputColumnOwner::SourceContract => (
            "source",
            "that source contract",
            "Declared contract columns",
        ),
        CursorInputColumnOwner::SourceWarehouse => {
            ("source", "that source", "Known source columns")
        }
    };
    let known: String = if check.known_columns.is_empty() {
        "none".to_owned()
    } else {
        check.known_columns.join(", ")
    };
    Some((
        format!(
            "model '{}': cursor_inputs references {kind} '{}' column '{}', but {exposer} does \
             not expose the column. {label}: {known}",
            check.model_name, check.input_name, check.column
        ),
        CURSOR_INPUT_COLUMN_ERROR_CODE,
    ))
}
