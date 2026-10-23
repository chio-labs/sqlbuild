//! Header string delimiters, prose values and quote failures.

/// How a header string is delimited.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HeaderQuote {
    /// `"""..."""`: the text is taken as written, quotes included.
    Triple,
    /// `"..."`.
    Double,
    /// `'...'`.
    Single,
}

/// One prose string of a header: where it is and the folded text it stores.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProseString {
    pub quote: HeaderQuote,
    /// Character offsets of the opening delimiter and just past the closing one.
    pub start: usize,
    pub end: usize,
    /// The folded text the header stores.
    pub value: String,
}

/// Why a triple-quoted string does not end where it should.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TripleQuoteError {
    /// No closing `"""` follows.
    Unclosed,
    /// A `"""` at this offset ends the string inside its text.
    Inside(usize),
}

/// A header quote error located in its file, with the message and help it reports.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QuoteFailure {
    /// The character offset of the offending quote in the header text.
    pub position: usize,
    /// One-based file line and column of the offending quote.
    pub line: usize,
    pub column: usize,
    pub message: String,
    pub help: String,
}
