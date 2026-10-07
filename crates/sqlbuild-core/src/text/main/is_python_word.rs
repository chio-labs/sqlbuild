//! A character of Python's `\w` for `str` patterns.

use crate::text::main::is_python_alnum::is_python_alnum;

/// Whether one character matches Python's `\w`: `str.isalnum()` or `_`.
pub fn is_python_word(character: char) -> bool {
    character == '_' || is_python_alnum(character)
}
