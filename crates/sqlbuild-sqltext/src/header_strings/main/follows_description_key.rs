//! Whether a header string is the value of a `description` key, which holds prose.

use crate::header_strings::_helpers::description_keys::{inside_meta, key_ends_at};
use crate::header_strings::constants::DESCRIPTION_KEY;

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
    key_end < start
        && key_ends_at(text, key_end, DESCRIPTION_KEY)
        && !inside_meta(text, key_end - DESCRIPTION_KEY.len(), is_space)
}
