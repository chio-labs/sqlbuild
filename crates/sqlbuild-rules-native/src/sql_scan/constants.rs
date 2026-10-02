//! Lexical vocabulary shared by SQL scanning.

/// Characters that may prefix a string literal, such as `E'...'` or `r'...'`.
pub(crate) const STRING_PREFIX_CHARACTERS: &[u8] = b"bBeErR";
/// Longest string-literal prefix, such as `rb`.
pub(crate) const STRING_PREFIX_MAX_LENGTH: usize = 2;
/// Length of a triple-quote string delimiter.
pub(crate) const TRIPLE_QUOTE_LENGTH: usize = 3;
