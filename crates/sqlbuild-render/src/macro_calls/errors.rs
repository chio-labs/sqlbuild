//! The errors Python's macro call scan raises.

/// An error Python's macro call scan raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScanError {
    UnclosedQuote,
    UnclosedComment,
    UnclosedParenthesis,
    /// A call start whose name is not followed by its parenthesis.
    MissingParenthesis,
    /// `@name(...)` without `py.` or `sql.`, which says which kind of macro it calls.
    BareCall,
    /// `@sql.name(...)` where only Python macro calls are expanded.
    SqlCall,
}

impl ScanError {
    /// The message of the `CompileInputError` Python's scan raises.
    pub fn message(self) -> &'static str {
        match self {
            Self::UnclosedQuote => "Macro expansion contains an unclosed quoted string",
            Self::UnclosedComment => "Macro expansion contains an unclosed block comment",
            Self::UnclosedParenthesis => "Macro expansion contains an unclosed parenthesis",
            Self::MissingParenthesis => "expected opening parenthesis",
            Self::BareCall => "macro call does not say which kind of macro it calls",
            Self::SqlCall => "SQL macro calls are not expanded here",
        }
    }
}
