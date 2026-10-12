//! A word character: a letter, a number or `_`.

use crate::text::main::is_python_alnum::is_python_alnum;

/// Whether `character` is `_` or alphanumeric.
pub fn is_python_word(character: char) -> bool {
    character == '_' || is_python_alnum(character)
}
