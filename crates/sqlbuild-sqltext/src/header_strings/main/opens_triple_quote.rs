//! Whether a triple-quoted header string opens at an offset.

use crate::header_strings::constants::TRIPLE_QUOTE_LENGTH;
use crate::header_strings::types::HeaderChar;

/// Whether `"""` starts at `index`.
pub fn opens_triple_quote<T: HeaderChar>(text: &[T], index: usize) -> bool {
    text.get(index..index + TRIPLE_QUOTE_LENGTH)
        .is_some_and(|delimiter| delimiter.iter().all(|unit| *unit == T::ascii(b'"')))
}
