//! Python's `str.isdecimal()`, the regex `\d` of `str` patterns, from a generated table.

use crate::text::main::is_python_alnum::in_ranges;
use crate::text::models::PythonText;

/// Whether Python's `str.isdecimal()` is true for one character.
pub fn is_python_decimal(python: PythonText, character: char) -> bool {
    if character.is_ascii() {
        return character.is_ascii_digit();
    }
    in_ranges(python.decimal_ranges, character)
}
