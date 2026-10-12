//! One SQL text scanned for code at Python string offsets.

use crate::sql_scan::models::LexicalSyntax;

/// A SQL text, its code point byte offsets and the dialect rules it is scanned under, if any.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeScanner {
    pub(crate) sql: String,
    /// The byte offset of each code point and then the text length; empty for ASCII text.
    pub(crate) char_bytes: Vec<usize>,
    /// Dialect rules; without them the compiler's generic quoting and comments apply.
    pub(crate) syntax: Option<LexicalSyntax>,
}
