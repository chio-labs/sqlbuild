//! Python's `str.strip()` without arguments.

use crate::text::main::is_python_space::is_python_space;

/// The text without leading and trailing Python whitespace.
pub fn python_strip(text: &str) -> &str {
    text.trim_matches(is_python_space)
}
