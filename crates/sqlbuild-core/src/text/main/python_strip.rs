//! Python's `str.strip()` with no arguments.

use crate::text::main::python_isspace::python_isspace;

/// Python's `text.strip()`.
#[must_use]
pub fn python_strip(text: &str) -> &str {
    text.trim_matches(python_isspace)
}
