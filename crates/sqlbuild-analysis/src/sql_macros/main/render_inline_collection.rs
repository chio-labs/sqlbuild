use crate::sql_macros::_helpers::arguments::{collection_items, collection_problem};
use crate::sql_macros::_helpers::lexing::{Token, tokens};
use crate::sql_macros::constants::ARGUMENT_CODE;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::TypeFamily;

/// An inline `[...]` list or `{...}` set, validated like a constant and rendered as a value list.
pub fn render_inline_collection(text: &str) -> Result<String, SqlMacroError> {
    let invalid = |reason: &str| {
        SqlMacroError::new(
            ARGUMENT_CODE,
            format!("inline collection {} {reason}", text.trim()),
        )
    };
    let scanned: Vec<Token> = tokens(text).map_err(|_| invalid("has an unclosed quote"))?;
    let (Some(open), Some(close)) = (scanned.first(), scanned.last()) else {
        return Err(invalid("is empty"));
    };
    let set: bool = open.is(text, "{");
    if !(open.is(text, "[") && close.is(text, "]") || set && close.is(text, "}")) {
        return Err(invalid("must be a [...] list or a {...} set"));
    }
    let items: Vec<(String, TypeFamily)> =
        collection_items(text, &scanned[1..scanned.len() - 1], &invalid)?;
    if let Some(problem) = collection_problem(&items, set) {
        return Err(invalid(&problem));
    }
    let rendered: Vec<String> = items.into_iter().map(|(value, _)| value).collect();
    Ok(format!("({})", rendered.join(", ")))
}
