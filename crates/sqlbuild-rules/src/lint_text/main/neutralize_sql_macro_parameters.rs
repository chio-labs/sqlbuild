//! `neutralize_sql_macro_parameters`: a SQL macro body's `@name` parameters replaced by sentinels.

use std::collections::HashMap;

use sqlbuild_analysis::sql_macros::main::sql_macro_parameter_spans::sql_macro_parameter_spans;
use sqlbuild_analysis::sql_macros::models::{ParameterSpan, SqlMacroParameter};

use crate::lint_text::_helpers::sites::{ByteSite, assemble, sentinel};
use crate::lint_text::constants::SQL_MACRO_PARAMETER_SENTINEL_PREFIX;
use crate::lint_text::models::Neutralized;

/// Replace each parameter reference with a sentinel; one `RELATION` parameter's relation spans share one.
pub fn neutralize_sql_macro_parameters(
    body: &str,
    parameters: &[SqlMacroParameter],
) -> Neutralized {
    let mut relations: HashMap<String, String> = HashMap::new();
    let mut next: usize = 0;
    let mut fresh = || {
        let made: String = sentinel(SQL_MACRO_PARAMETER_SENTINEL_PREFIX, next);
        next += 1;
        made
    };
    let byte_sites: Vec<ByteSite> = sql_macro_parameter_spans(body, parameters)
        .into_iter()
        .map(|span: ParameterSpan| {
            let replacement: String = match span.relation {
                Some(relation) => relations.entry(relation).or_insert_with(&mut fresh).clone(),
                None => fresh(),
            };
            (span.start, span.end, replacement)
        })
        .collect();
    assemble(body, byte_sites)
}
