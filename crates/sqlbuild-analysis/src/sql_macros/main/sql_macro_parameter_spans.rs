//! The byte spans of a SQL macro body's `@name` parameter references, as expansion reads them.

use crate::sql_macros::_helpers::parsing::lexing::tokens;
use crate::sql_macros::_helpers::parsing::parameters::parameter_references;

/// The `start..end` byte span of each `@name` in `body` that expansion replaces by an argument.
#[must_use]
pub fn sql_macro_parameter_spans(body: &str) -> Vec<(usize, usize)> {
    let Ok(scanned) = tokens(body) else {
        return Vec::new();
    };
    parameter_references(body, &scanned)
        .into_iter()
        .map(|reference| (reference.start, reference.end))
        .collect()
}
