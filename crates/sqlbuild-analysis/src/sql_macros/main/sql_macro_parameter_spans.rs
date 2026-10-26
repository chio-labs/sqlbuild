//! The byte spans of a SQL macro body's `@name` parameter references, as expansion reads them.

use crate::sql_macros::_helpers::parsing::header::unquoted;
use crate::sql_macros::_helpers::parsing::lexing::{Token, TokenKind, tokens};
use crate::sql_macros::_helpers::parsing::parameters::parameter_references;
use crate::sql_macros::_helpers::parsing::slots::prefix_start;
use crate::sql_macros::models::{ParameterSpan, SqlMacroParameter};

/// Each `@name` span expansion replaces: aliased and plain group reads whole, other plain reads as relation and slot.
#[must_use]
pub fn sql_macro_parameter_spans(
    body: &str,
    parameters: &[SqlMacroParameter],
) -> Vec<ParameterSpan> {
    let Ok(scanned) = tokens(body) else {
        return Vec::new();
    };
    let relation = |name: &str| -> Option<&SqlMacroParameter> {
        parameters
            .iter()
            .find(|parameter| parameter.name.eq_ignore_ascii_case(name))
            .filter(|parameter| parameter.kind.declares_relation())
    };
    let mut spans: Vec<ParameterSpan> = Vec::new();
    for reference in parameter_references(body, &scanned) {
        let name: usize = reference.token;
        let declared: Option<&SqlMacroParameter> = relation(&reference.name);
        let named_relation: Option<String> =
            declared.map(|parameter| parameter.name.to_lowercase());
        let Some(slot) = slot_word(body, &scanned, name) else {
            spans.push(ParameterSpan {
                start: reference.start,
                end: reference.end,
                relation: named_relation,
            });
            continue;
        };
        let slot_name: String = unquoted(slot.text(body));
        let qualified: bool = name >= 1 && prefix_start(body, &scanned, name - 1).is_some();
        let group: bool =
            declared.is_some_and(|parameter| parameter.kind.declares_group(&slot_name));
        if qualified || group {
            spans.push(ParameterSpan {
                start: reference.start,
                end: slot.end,
                relation: None,
            });
            continue;
        }
        spans.push(ParameterSpan {
            start: reference.start,
            end: reference.end,
            relation: named_relation,
        });
        spans.push(ParameterSpan {
            start: slot.start,
            end: slot.end,
            relation: None,
        });
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
