//! The byte spans of a SQL macro body's `@name` parameter references, as expansion reads them.

use crate::sql_macros::_helpers::parsing::lexing::{Token, TokenKind, tokens};
use crate::sql_macros::_helpers::parsing::parameters::parameter_references;
use crate::sql_macros::_helpers::parsing::slots::prefix_start;

/// The span of each `@name` expansion replaces, and of each slot name whose column a call maps.
#[must_use]
pub fn sql_macro_parameter_spans(body: &str) -> Vec<(usize, usize)> {
    let Ok(scanned) = tokens(body) else {
        return Vec::new();
    };
    let mut spans: Vec<(usize, usize)> = Vec::new();
    for reference in parameter_references(body, &scanned) {
        let name: usize = reference.token;
        let Some(slot) = slot_word(body, &scanned, name) else {
            spans.push((reference.start, reference.end));
            continue;
        };
        if name >= 1 && prefix_start(body, &scanned, name - 1).is_some() {
            spans.push((reference.start, slot.end));
            continue;
        }
        spans.push((reference.start, reference.end));
        spans.push((slot.start, slot.end));
    }
    spans
}

/// The slot name directly after the `.` that follows the parameter name at token `name`, if any.
fn slot_word<'t>(body: &str, scanned: &'t [Token], name: usize) -> Option<&'t Token> {
    let dot: &Token = scanned.get(name + 1)?;
    let word: &Token = scanned.get(name + 2)?;
    let joined: bool = dot.is(body, ".")
        && dot.start == scanned[name].end
        && matches!(word.kind, TokenKind::Word | TokenKind::Quoted)
        && word.start == dot.end;
    joined.then_some(word)
}
