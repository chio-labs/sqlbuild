//! Python's `unicodedata.decimal` for the characters `str.isdecimal()` accepts.

use crate::text::models::PythonText;

/// The digit value Python's `int()` reads from one character, if `str.isdecimal()` is true.
///
/// Every generated decimal range starts at a zero digit and runs in blocks of ten.
pub fn python_decimal_value(python: PythonText, character: char) -> Option<u32> {
    if character.is_ascii() {
        return character.to_digit(10);
    }
    let code_point: u32 = u32::from(character);
    let index: usize = python
        .decimal_ranges
        .partition_point(|(_, end)| *end < code_point);
    let (start, _) = python
        .decimal_ranges
        .get(index)
        .filter(|(start, _)| *start <= code_point)?;
    Some((code_point - start) % 10)
}
