//! The P010 message of a named resource without a non-empty description.

use sqlbuild_core::text::main::python_strip::python_strip;

/// `<kind> '<name>' has no description` or `... has an empty description`, if missing.
#[must_use]
pub fn missing_description(kind: &str, name: &str, description: Option<&str>) -> Option<String> {
    let state: &str = match description {
        None => "has no description",
        Some(text) if python_strip(text).is_empty() => "has an empty description",
        Some(_) => return None,
    };
    Some(format!("{kind} '{name}' {state}"))
}
