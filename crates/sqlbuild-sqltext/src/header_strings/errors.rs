//! Why a triple-quoted header string does not end where it should.

/// Why a triple-quoted string does not end where it should.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TripleQuoteError {
    /// No closing `"""` follows.
    Unclosed,
    /// A `"""` at this offset ends the string inside its text.
    Inside(usize),
}
