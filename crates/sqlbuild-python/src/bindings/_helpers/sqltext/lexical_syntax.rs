//! One adapter's `SqlLexicalSyntax`, read from a Python mapping.

use pyo3::FromPyObject;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

/// One adapter's `SqlLexicalSyntax`, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct LexicalSyntaxInput {
    backslash_escape_quotes: Vec<String>,
    escape_string_prefix: bool,
    raw_string_prefix: bool,
    triple_quoted_strings: bool,
    nested_block_comments: bool,
    line_comment_prefixes: Vec<String>,
}

impl From<LexicalSyntaxInput> for LexicalSyntax {
    fn from(input: LexicalSyntaxInput) -> Self {
        Self {
            backslash_escape_quotes: input.backslash_escape_quotes,
            escape_string_prefix: input.escape_string_prefix,
            raw_string_prefix: input.raw_string_prefix,
            triple_quoted_strings: input.triple_quoted_strings,
            nested_block_comments: input.nested_block_comments,
            line_comment_prefixes: input.line_comment_prefixes,
        }
    }
}
