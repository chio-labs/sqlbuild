//! Python's compiler scan of comments and quoted text outside any adapter dialect.

use sqlbuild_sqltext::sql_scan::main::comment_end::comment_end;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;

use crate::sql_lexing::_helpers::quotes::{DOLLAR_POLICY, quoted_end};
use crate::sql_lexing::models::NonCode;

/// Python's comment, quote and `$tag$` skipping at `index`; a `$` opening nothing is code.
#[must_use]
pub fn python_non_code_end(bytes: &[u8], index: usize) -> NonCode {
    match comment_end(bytes, index) {
        Ok(Some(end)) => return NonCode::End(end),
        Ok(None) => {}
        Err(_) => return NonCode::Raises,
    }
    match bytes.get(index) {
        Some(quote @ (b'\'' | b'"' | b'`')) => {
            quoted_end(bytes, index, *quote).map_or(NonCode::Raises, NonCode::End)
        }
        Some(b'$') => match non_code_end(bytes, index, DOLLAR_POLICY) {
            Ok(Some(end)) => NonCode::End(end),
            Ok(None) => NonCode::Code,
            Err(_) => NonCode::Raises,
        },
        _ => NonCode::Code,
    }
}
