//! Text that cannot be encoded where Python's capture encodes it.

/// Python's `UnicodeEncodeError` for text holding a surrogate the capture must encode.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UnencodableText {
    /// Code point index of the first surrogate that failed to encode.
    pub position: usize,
    /// The surrogate's code point.
    pub code_point: u32,
}
