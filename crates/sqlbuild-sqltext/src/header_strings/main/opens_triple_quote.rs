//! Whether a triple-quoted header string opens at an offset.

use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;

/// Whether `"""` starts at `index`.
pub fn opens_triple_quote<T: Copy + PartialEq + From<u8>>(text: &[T], index: usize) -> bool {
    text.get(index..index + TRIPLE_QUOTE_LENGTH)
        .is_some_and(|delimiter| delimiter.iter().all(|unit| *unit == T::from(b'"')))
}
