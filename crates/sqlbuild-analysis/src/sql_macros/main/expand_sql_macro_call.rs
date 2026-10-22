use crate::sql_macros::_helpers::lexing::{Token, tokens};
use crate::sql_macros::constants::INVALID_DEFINITION_CODE;
use crate::sql_macros::errors::ExpansionFailure;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{InsertedNames, SqlMacroCall, TextContext};
use crate::sql_macros::types::SqlMacroHost;

/// One outer SQL macro call's replacement text, and the names inserted so far.
pub fn expand_sql_macro_call<H: SqlMacroHost>(
    host: &H,
    context: &TextContext<'_>,
    inserted: InsertedNames,
    call: &SqlMacroCall,
) -> Result<(String, InsertedNames), ExpansionFailure<H::Error>> {
    let scanned: Vec<Token> = tokens(context.text).map_err(|_| {
        SqlMacroError::new(
            INVALID_DEFINITION_CODE,
            "SQL has an unclosed quote or comment",
        )
    })?;
    crate::sql_macros::_helpers::expansion::expand_call(host, context, (&scanned, inserted), call)
}
