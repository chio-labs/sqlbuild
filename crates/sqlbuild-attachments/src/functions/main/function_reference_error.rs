//! `validate_function_references`: the error Python raises for a SQL function's bad reference.

use crate::functions::_helpers::references::reference_problem;
use crate::functions::models::KnownResources;

/// The error for the first of `references` (`(kind, name)`) the project cannot resolve.
#[must_use]
pub fn function_reference_error(
    relative_path: &str,
    references: &[(&str, &str)],
    known: &KnownResources<'_>,
) -> Option<String> {
    for &(kind, name) in references {
        if let Some(problem) = reference_problem(kind, name, known) {
            return Some(format!("SQL function file {relative_path} {problem}"));
        }
    }
    None
}
