//! `validate_table_function_call_arities`: a managed table function called with the wrong count.

use std::collections::HashMap;

use crate::functions::constants::TABLE_FUNCTION_KIND;

/// The first `(kind, name, argument count)` call whose count differs from the declared one.
#[must_use]
pub fn table_function_arity_error(
    owner: &str,
    calls: &[(&str, &str, Option<usize>)],
    argument_counts: &HashMap<String, usize>,
) -> Option<String> {
    calls.iter().find_map(|&(kind, name, received)| {
        if kind != TABLE_FUNCTION_KIND {
            return None;
        }
        let expected: usize = *argument_counts.get(name)?;
        if received == Some(expected) {
            return None;
        }
        let label: &str = if expected == 1 {
            "argument"
        } else {
            "arguments"
        };
        let received: String =
            received.map_or_else(|| "None".to_owned(), |count| count.to_string());
        Some(format!(
            "{owner} table function '{name}' expects {expected} {label} but received {received}"
        ))
    })
}
