use crate::sql_macros::_helpers::parsing::header::unquoted;
use crate::sql_macros::_helpers::parsing::lexing::{Token, TokenKind, tokens};
use crate::sql_macros::constants::ITEM_ENDS;
use crate::sql_macros::models::TypedCall;

/// The `(output name, macro name)` of each select item that is one untyped macro call.
#[must_use]
pub fn untyped_call_outputs(sql: &str, calls: &[TypedCall]) -> Vec<(String, String)> {
    let untyped: Vec<&TypedCall> = calls
        .iter()
        .filter(|call| call.returns.is_none() && call.returns_like.is_none())
        .collect();
    if untyped.is_empty() {
        return Vec::new();
    }
    let Ok(scanned) = tokens(sql) else {
        return Vec::new();
    };
    let mut outputs: Vec<(String, String)> = Vec::new();
    for call in untyped {
        let Some(first) = scanned.iter().position(|token| token.start == call.start) else {
            continue;
        };
        let opens_item: bool = first.checked_sub(1).is_some_and(|before| {
            let token: &Token = &scanned[before];
            token.is(sql, ",") || token.is_word(sql, "SELECT") || token.is_word(sql, "DISTINCT")
        });
        let Some(after) = scanned.iter().position(|token| token.start >= call.end) else {
            continue;
        };
        if !opens_item {
            continue;
        }
        let alias: usize = if scanned[after].is_word(sql, "AS") {
            after + 1
        } else {
            after
        };
        let Some(name) = scanned.get(alias).filter(|token| {
            matches!(token.kind, TokenKind::Word | TokenKind::Quoted) && !ends_item(token, sql)
        }) else {
            continue;
        };
        let closes_item: bool = scanned
            .get(alias + 1)
            .is_none_or(|next| next.is(sql, ",") || next.kind == TokenKind::Word);
        if closes_item {
            outputs.push((unquoted(name.text(sql)), call.macro_name.clone()));
        }
    }
    outputs
}

/// Whether `token` is a word that ends a select item rather than aliases it.
fn ends_item(token: &Token, sql: &str) -> bool {
    ITEM_ENDS.iter().any(|word| token.is_word(sql, word))
}
