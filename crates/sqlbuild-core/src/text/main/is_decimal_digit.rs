//! Whether one character is a decimal digit in any script.

use crate::text::_helpers::decimal_digits::decimal_digit;

/// Whether `character` is a Unicode decimal digit (`Nd`), as `str.isdecimal()` reads it.
pub fn is_decimal_digit(character: char) -> bool {
    decimal_digit(character).is_some()
}
