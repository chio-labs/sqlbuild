//! Which authored tokens are case-insensitive keywords or built-in function names.

use polyglot_sql::Dialect;
use polyglot_sql::tokens::Token;

use crate::sql_tokens::_helpers::token_context::TokenContext;
use crate::sql_tokens::main::name_positions::name_positions;

/// Return, for every token, whether the formatter may recase it and the fingerprint folds it.
pub(crate) fn foldable_tokens(raws: &[String], tokens: &[Token], dialect: &Dialect) -> Vec<bool> {
    let uppers: Vec<String> = raws.iter().map(|raw| raw.to_ascii_uppercase()).collect();
    let names = name_positions(&uppers);
    let mut foldable = Vec::with_capacity(tokens.len());
    for (index, name) in names.iter().enumerate().take(tokens.len()) {
        let context = TokenContext {
            raws,
            uppers: &uppers,
            index,
        };
        foldable.push(!name && context.is_foldable(dialect.dialect_type()));
    }
    foldable
}
