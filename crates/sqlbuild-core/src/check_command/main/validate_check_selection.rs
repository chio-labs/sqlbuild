//! Refuse a check selection that resolved to Python nodes other than checks.

use crate::check_command::constants::SELECTION_CODE;
use crate::check_command::errors::CheckSelectionError;

/// C682 naming the sorted non-check selections, when there are any.
pub fn validate_check_selection(non_check_names: &[String]) -> Result<(), CheckSelectionError> {
    if non_check_names.is_empty() {
        return Ok(());
    }
    let mut names: Vec<&str> = non_check_names.iter().map(String::as_str).collect();
    names.sort_unstable();
    Err(CheckSelectionError {
        code: SELECTION_CODE,
        message: format!(
            "sqb check selectors must resolve only to Python checks; non-check selections: {}",
            names.join(", ")
        ),
    })
}
