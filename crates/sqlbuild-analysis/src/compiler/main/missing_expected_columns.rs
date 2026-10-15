//! Explain expected-output columns that a model does not produce.

use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::compiler::constants::SQL_TEST_IDENTIFIER_QUOTES;

/// The message for listed expected columns absent from casefolded model output names, if any.
#[must_use]
pub fn missing_expected_columns(
    model_name: &str,
    expected_columns: &[String],
    available_columns: &[String],
) -> Option<String> {
    let missing: Vec<&str> = expected_columns
        .iter()
        .filter(|column| !available_columns.contains(&normalized_identifier(column)))
        .map(String::as_str)
        .collect();
    if missing.is_empty() {
        return None;
    }
    Some(format!(
        "expected output '{model_name}' lists columns that model '{model_name}' does not output: {}. Expected CTEs are compared only on the columns they list, matched by name",
        missing.join(", ")
    ))
}

fn normalized_identifier(identifier: &str) -> String {
    let closing: Option<char> = identifier.chars().next().and_then(|first| {
        SQL_TEST_IDENTIFIER_QUOTES
            .iter()
            .find(|(open, _)| *open == first)
            .map(|(_, close)| *close)
    });
    match closing {
        Some(close) if identifier.ends_with(close) => {
            let inner: &str = identifier.get(1..identifier.len() - 1).unwrap_or_default();
            let doubled: String = [close, close].iter().collect();
            python_casefold(&inner.replace(&doubled, &close.to_string()))
        }
        _ => python_casefold(identifier),
    }
}
