//! Errors of decoding authored text.

/// Authored bytes that are not valid UTF-8; `valid_up_to` is the longest valid prefix.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TextDecodeError {
    pub valid_up_to: usize,
    /// The length of the invalid sequence, or `None` when the bytes end mid-sequence.
    pub error_len: Option<usize>,
}
