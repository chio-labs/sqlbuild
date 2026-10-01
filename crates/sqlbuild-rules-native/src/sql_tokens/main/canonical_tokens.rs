//! Canonical token stream of SQL text under one dialect tokenizer.

use polyglot_sql::Dialect;
use polyglot_sql::tokens::Token;

use crate::sql_tokens::main::case_folding::foldable_tokens;
use crate::sql_tokens::main::token_texts::token_texts;
use crate::sql_tokens::models::CanonicalToken;

/// Drop whitespace and comments from tokenized `sql` and upper-case case-insensitive tokens.
pub(crate) fn canonical_tokens(
    sql: &str,
    tokens: &[Token],
    dialect: &Dialect,
) -> Result<Vec<CanonicalToken>, String> {
    let raws = token_texts(sql, tokens)?;
    let foldable = foldable_tokens(&raws, tokens, dialect);
    Ok(raws
        .into_iter()
        .zip(foldable)
        .map(|(raw, fold)| CanonicalToken {
            text: if fold { raw.to_ascii_uppercase() } else { raw },
        })
        .collect())
}
