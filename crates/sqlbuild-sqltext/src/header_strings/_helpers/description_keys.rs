//! Header keys around a string: whole-word key matches and enclosing `meta` values.

use crate::header_strings::constants::META_KEY;

/// Whether `unit` can be part of a header key.
fn is_key_unit<T: Into<u32>>(unit: T) -> bool {
    char::from_u32(unit.into())
        .is_some_and(|character| character.is_alphanumeric() || character == '_')
}

/// Whether `text` holds `key`, in any letter case, as a whole word ending at `end`.
pub(crate) fn key_ends_at<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    end: usize,
    key: &str,
) -> bool {
    let Some(start) = end.checked_sub(key.len()) else {
        return false;
    };
    let matches_key: bool = key.bytes().enumerate().all(|(offset, byte)| {
        let unit: T = text[start + offset];
        unit == T::from(byte) || unit == T::from(byte.to_ascii_uppercase())
    });
    matches_key && (start == 0 || !is_key_unit(text[start - 1]))
}

/// Whether the key ending before `end` sits inside a `meta (...)` value, which holds no prose.
pub(crate) fn inside_meta<T: Copy + PartialEq + From<u8> + Into<u32>>(
    text: &[T],
    end: usize,
    is_space: impl Fn(T) -> bool,
) -> bool {
    let mut depth: usize = 0;
    for index in (0..end).rev() {
        if text[index] == T::from(b')') {
            depth += 1;
        } else if text[index] == T::from(b'(') {
            if depth > 0 {
                depth -= 1;
                continue;
            }
            let mut key_end: usize = index;
            while key_end > 0 && is_space(text[key_end - 1]) {
                key_end -= 1;
            }
            if key_ends_at(text, key_end, META_KEY) {
                return true;
            }
        }
    }
    false
}
