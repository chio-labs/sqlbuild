//! Canonical token stream of SQL text under one dialect tokenizer.

use polyglot_sql::Dialect;

use crate::sql_tokens::main::is_unquoted_word::is_unquoted_word;
use crate::sql_tokens::models::CanonicalToken;

/// Tokenize `sql`, dropping whitespace and comments and upper-casing unquoted words.
pub(crate) fn canonical_tokens(
    sql: &str,
    dialect: &Dialect,
) -> Result<Vec<CanonicalToken>, String> {
    let tokens = dialect
        .tokenize(sql)
        .map_err(|error| format!("SQL tokenization failed: {error}"))?;
    let characters: Vec<char> = sql.chars().collect();
    tokens
        .iter()
        .map(|token| {
            let raw: String = characters
                .get(token.span.start..token.span.end)
                .ok_or_else(|| "SQL tokenizer returned an invalid token span".to_string())?
                .iter()
                .collect();
            let text = if is_unquoted_word(&raw) {
                raw.to_ascii_uppercase()
            } else {
                raw
            };
            Ok(CanonicalToken { text })
        })
        .collect()
}
