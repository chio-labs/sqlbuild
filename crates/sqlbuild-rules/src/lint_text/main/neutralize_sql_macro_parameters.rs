//! `neutralize_sql_macro_parameters`: a SQL macro body's `@name` parameters replaced by sentinels.

use sqlbuild_analysis::sql_macros::main::sql_macro_parameter_spans::sql_macro_parameter_spans;

use crate::lint_text::_helpers::sites::{ByteSite, assemble, sentinel};
use crate::lint_text::constants::SQL_MACRO_PARAMETER_SENTINEL_PREFIX;
use crate::lint_text::models::Neutralized;

/// Replace each parameter reference expansion would replace, and nothing else, with a sentinel.
pub fn neutralize_sql_macro_parameters(body: &str) -> Neutralized {
    let byte_sites: Vec<ByteSite> = sql_macro_parameter_spans(body)
        .into_iter()
        .enumerate()
        .map(|(index, (start, end))| {
            (
                start,
                end,
                sentinel(SQL_MACRO_PARAMETER_SENTINEL_PREFIX, index),
            )
        })
        .collect();
    assemble(body, byte_sites)
}
