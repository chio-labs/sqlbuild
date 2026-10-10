//! The errors Python's macro call scan raises.

/// An error Python's macro call scan raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScanError {
    UnclosedQuote,
    UnclosedComment,
    UnclosedParenthesis,
    /// A call start whose name is not followed by its parenthesis.
    MissingParenthesis,
}

impl ScanError {
    /// The message of the `CompileInputError` Python's scan raises.
    pub fn message(self) -> &'static str {
        match self {
            Self::UnclosedQuote => "Macro expansion contains an unclosed quoted string",
            Self::UnclosedComment => "Macro expansion contains an unclosed block comment",
            Self::UnclosedParenthesis => "Macro expansion contains an unclosed parenthesis",
            Self::MissingParenthesis => "expected opening parenthesis",
        }
    }
}
