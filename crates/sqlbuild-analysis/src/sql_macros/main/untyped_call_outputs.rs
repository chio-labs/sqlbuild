use crate::sql_macros::_helpers::header::unquoted;
use crate::sql_macros::_helpers::lexing::{Token, TokenKind, tokens};
use crate::sql_macros::models::TypedCall;

/// Words that end a select item rather than alias it.
const ITEM_ENDS: [&str; 4] = ["FROM", "WHERE", "UNION", "ORDER"];

/// Each named select item of `sql` that is exactly one call to a macro without `returns`, as
/// `(output name, macro name)`.
#[must_use]
pub fn untyped_call_outputs(sql: &str, calls: &[TypedCall]) -> Vec<(String, String)> {
    let untyped: Vec<&TypedCall> = calls.iter().filter(|call| call.returns.is_none()).collect();
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
            matches!(token.kind, TokenKind::Word | TokenKind::Quoted)
                && !ITEM_ENDS.iter().any(|word| token.is_word(sql, word))
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
