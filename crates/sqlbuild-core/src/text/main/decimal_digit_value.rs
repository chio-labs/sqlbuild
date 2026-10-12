//! The value of one decimal digit in any script.

use crate::text::_helpers::decimal_digits::decimal_digit;

/// The value of a Unicode decimal digit, as `unicodedata.decimal` reads it.
pub fn decimal_digit_value(character: char) -> Option<u32> {
    decimal_digit(character)
}
