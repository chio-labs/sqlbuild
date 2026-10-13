//! `neutralize_context_interpolation`: runtime `@@CTX:` interpolation replaced by sentinels.

use crate::lint_text::_helpers::sites::{ByteSite, assemble, name_end, sentinel};
use crate::lint_text::constants::{CONTEXT_INTERPOLATION_TOKEN, CONTEXT_SENTINEL_PREFIX};
use crate::lint_text::models::Neutralized;

/// Replace every `@@CTX:` interpolation with a parseable generated sentinel.
pub fn neutralize_context_interpolation(body: &str) -> Neutralized {
    let mut byte_sites: Vec<ByteSite> = Vec::new();
    let mut copied_to: usize = 0;
    while let Some(found) = body[copied_to..].find(CONTEXT_INTERPOLATION_TOKEN) {
        let start: usize = copied_to + found;
        let end: usize = name_end(body, start + 2, true);
        byte_sites.push((
            start,
            end,
            sentinel(CONTEXT_SENTINEL_PREFIX, byte_sites.len()),
        ));
        copied_to = end;
    }
    assemble(body, byte_sites)
}
