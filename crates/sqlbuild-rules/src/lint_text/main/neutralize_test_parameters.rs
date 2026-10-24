//! `neutralize_test_parameters`: SQL test `@param("name")` references replaced by sentinels.

use crate::lint_text::_helpers::sites::{ByteSite, assemble, sentinel};
use crate::lint_text::constants::{TEST_PARAMETER_SENTINEL_PREFIX, TEST_PARAMETER_TOKEN};
use crate::lint_text::models::Neutralized;

/// Replace each `@param("name")` with a string sentinel, as every case supplies a literal there.
pub fn neutralize_test_parameters(body: &str) -> Neutralized {
    let mut byte_sites: Vec<ByteSite> = Vec::new();
    let mut searched_to: usize = 0;
    while let Some(found) = body[searched_to..].find(TEST_PARAMETER_TOKEN) {
        let start: usize = searched_to + found;
        searched_to = start + TEST_PARAMETER_TOKEN.len();
        let Some(end) = reference_end(body, searched_to) else {
            continue;
        };
        let identifier: String = sentinel(TEST_PARAMETER_SENTINEL_PREFIX, byte_sites.len());
        byte_sites.push((start, end, format!("'{identifier}'")));
        searched_to = end;
    }
    assemble(body, byte_sites)
}

/// The end of `("name")` after `@param` at `start`, spaces allowed around its parts.
fn reference_end(body: &str, start: usize) -> Option<usize> {
    let bytes: &[u8] = body.as_bytes();
    let skip_spaces = |mut index: usize| {
        while bytes.get(index).is_some_and(u8::is_ascii_whitespace) {
            index += 1;
        }
        index
    };
    let mut index: usize = skip_spaces(start);
    (bytes.get(index) == Some(&b'(')).then_some(())?;
    index = skip_spaces(index + 1);
    (bytes.get(index) == Some(&b'"')).then_some(())?;
    index += 1 + body[index + 1..].find('"')?;
    index = skip_spaces(index + 1);
    (bytes.get(index) == Some(&b')')).then_some(index + 1)
}
