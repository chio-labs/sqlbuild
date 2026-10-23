use crate::sql_macros::_helpers::expansion::sql_macro_calls;
use crate::sql_macros::_helpers::lexing::{Token, tokens};
use crate::sql_macros::_helpers::placement::{CallSite, QueryParts, top_level_parts};
use crate::sql_macros::models::{CallScope, SqlMacroCall};

/// The `(top-level CTE, branch, alias)` of each select item of `text` that is one SQL macro call.
#[must_use]
pub fn sql_macro_output_names(text: &str) -> Vec<(Option<String>, usize, String)> {
    let Ok(calls) = sql_macro_calls(text) else {
        return Vec::new();
    };
    if calls.is_empty() {
        return Vec::new();
    }
    let Ok(scanned) = tokens(text) else {
        return Vec::new();
    };
    let Some(parts) = top_level_parts(text, &scanned) else {
        return Vec::new();
    };
    calls
        .iter()
        .filter(|call| !call.in_python)
        .filter_map(|call| whole_item(text, (&scanned, &parts), call))
        .collect()
}

/// The `(top-level CTE, branch, alias)` of `call` when it is a whole aliased select item.
fn whole_item(
    text: &str,
    (scanned, parts): (&[Token], &QueryParts),
    call: &SqlMacroCall,
) -> Option<(Option<String>, usize, String)> {
    let cte: Option<String> = match parts.scope_of(call.start) {
        CallScope::Main => None,
        CallScope::Cte(name) => Some(name),
        CallScope::WithList => return None,
    };
    let branch: usize = parts.branch_of(text, scanned, call.start)?;
    CallSite::new(text, scanned, (call.start, call.end), call.replaced_end)
        .whole_item_alias()
        .map(|alias| (cte, branch, alias))
}
