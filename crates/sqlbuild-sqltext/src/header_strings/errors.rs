//! Why a header string does not end where it should.

/// Why a triple-quoted string does not end where it should.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TripleQuoteError {
    /// No closing `"""` follows.
    Unclosed,
    /// A `"""` at this offset ends the string inside its text.
    Inside(usize),
}

/// Why a prose header string does not end where it should.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProseError {
    /// The `"..."` or `'...'` string opening at this offset never closes.
    Unterminated(usize),
    /// A `"` at this offset ends a `"..."` string inside its text.
    DoubleQuoteInside(usize),
    /// A `'` at this offset ends a `'...'` string inside its text.
    SingleQuoteInside(usize),
    /// A `"""` at this offset ends a `"""..."""` string inside its text.
    TripleQuoteInside(usize),
    /// The `"""` string opening at this offset never closes.
    UnclosedTripleQuote(usize),
}
