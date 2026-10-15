//! The process-stable text key of one dialect's lexical rules.

use crate::sql_scan::models::LexicalSyntax;

/// `SqlLexicalSyntax.cache_key`: sorted quotes, the four flags as Python booleans, sorted prefixes.
#[must_use]
pub fn lexical_syntax_key(syntax: &LexicalSyntax) -> String {
    let flag = |value: bool| if value { "True" } else { "False" };
    let mut quotes: Vec<&str> = syntax
        .backslash_escape_quotes
        .iter()
        .map(String::as_str)
        .collect();
    quotes.sort_unstable();
    let mut prefixes: Vec<&str> = syntax
        .line_comment_prefixes
        .iter()
        .map(String::as_str)
        .collect();
    prefixes.sort_unstable();
    [
        quotes.join(","),
        flag(syntax.escape_string_prefix).to_owned(),
        flag(syntax.raw_string_prefix).to_owned(),
        flag(syntax.triple_quoted_strings).to_owned(),
        flag(syntax.nested_block_comments).to_owned(),
        prefixes.join(","),
    ]
    .join("|")
}
