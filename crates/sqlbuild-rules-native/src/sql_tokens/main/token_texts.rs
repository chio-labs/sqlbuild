//! Authored text of tokens, taken from their character spans.

use polyglot_sql::tokens::Token;

/// Return the authored text of every token in `sql`.
pub(crate) fn token_texts(sql: &str, tokens: &[Token]) -> Result<Vec<String>, String> {
    let characters: Vec<char> = sql.chars().collect();
    let mut texts = Vec::with_capacity(tokens.len());
    for token in tokens {
        let slice = characters
            .get(token.span.start..token.span.end)
            .ok_or_else(|| "SQL tokenizer returned an invalid token span".to_string())?;
        texts.push(slice.iter().collect());
    }
    Ok(texts)
}
