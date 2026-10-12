//! Python's `str.isdigit` for one character.

use crate::text::_helpers::python_tables::{PYTHON_NON_DECIMAL_DIGITS, in_ranges};
use crate::text::main::is_decimal_digit::is_decimal_digit;

/// Whether Python's `str.isdigit` accepts `character`: decimal digits and digit characters.
#[must_use]
pub fn python_isdigit(character: char) -> bool {
    is_decimal_digit(character) || in_ranges(&PYTHON_NON_DECIMAL_DIGITS, character)
}
