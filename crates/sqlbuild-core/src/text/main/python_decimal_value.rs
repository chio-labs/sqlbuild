//! The digit value of one Python decimal character, from a generated table.

use crate::text::_helpers::code_point_ranges::range_start;
use crate::text::models::PythonText;

/// The digit Python's `unicodedata.decimal()` gives one character, or `None` for a non-digit.
///
/// Decimal digits come in contiguous runs from zero to nine, so a merged table range starts at a
/// zero and the value is the distance from it, modulo ten.
pub fn python_decimal_value(python: PythonText, character: char) -> Option<u32> {
    if character.is_ascii() {
        return character.to_digit(10);
    }
    range_start(python.decimal_ranges, character).map(|start| (u32::from(character) - start) % 10)
}
