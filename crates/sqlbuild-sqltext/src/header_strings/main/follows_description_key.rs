//! Whether a header string is the value of a `description` key, which holds prose.

use crate::header_strings::constants::DESCRIPTION_KEY;

/// Whether `unit` can be part of a header key.
fn is_key_unit<T: Into<u32>>(unit: T) -> bool {
    char::from_u32(unit.into())
        .is_some_and(|character| character.is_alphanumeric() || character == '_')
}

/// Whether the string at `start` directly follows a `description` key, in any letter case.
pub fn follows_description_key<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    start: usize,
) -> bool {
    let is_space = |unit: T| b" \t\r\n".iter().any(|byte| unit == T::from(*byte));
    let mut key_end: usize = start;
    while key_end > 0 && is_space(text[key_end - 1]) {
        key_end -= 1;
    }
    let Some(key_start) = key_end.checked_sub(DESCRIPTION_KEY.len()) else {
        return false;
    };
    let matches_key: bool = DESCRIPTION_KEY.bytes().enumerate().all(|(offset, byte)| {
        let unit: T = text[key_start + offset];
        unit == T::from(byte) || unit == T::from(byte.to_ascii_uppercase())
    });
    matches_key && key_end < start && (key_start == 0 || !is_key_unit(text[key_start - 1]))
}
