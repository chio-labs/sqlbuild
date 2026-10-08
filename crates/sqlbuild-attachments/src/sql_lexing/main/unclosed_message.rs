//! Python's message for a construct its scan reaches the end of input inside.

use sqlbuild_sqltext::sql_scan::models::Unclosed;

/// Python's `"{context} contains an unclosed quoted string"` or block comment message.
#[must_use]
pub fn unclosed_message(context: &str, construct: Unclosed) -> String {
    let construct: &str = match construct {
        Unclosed::BlockComment => "block comment",
        Unclosed::Quote => "quoted string",
        Unclosed::Parenthesis => "parenthesis",
    };
    format!("{context} contains an unclosed {construct}")
}
