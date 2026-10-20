//! Python `repr` of a tuple of strings, as `rules show` prints a string-list option default.

use crate::rule_catalogue::_helpers::python_repr::string_repr;

/// `repr(tuple(items))`: `()`, `('a',)` or `('a', 'b')`.
#[must_use]
pub fn string_tuple_repr(items: &[&str]) -> String {
    let parts: Vec<String> = items.iter().map(|item| string_repr(item)).collect();
    match parts.as_slice() {
        [only] => format!("({only},)"),
        _ => format!("({})", parts.join(", ")),
    }
}
