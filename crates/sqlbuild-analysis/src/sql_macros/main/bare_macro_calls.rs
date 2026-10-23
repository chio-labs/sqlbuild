use crate::sql_macros::_helpers::lexing::{AtConstruct, at_constructs};
use crate::sql_macros::constants::NON_ASCII_BYTE;

/// The name and byte offset of each `@name(...)` call in `text` that names no macro kind.
#[must_use]
pub fn bare_macro_calls(text: &str) -> Vec<(String, usize)> {
    if !may_hold_bare_call(text.as_bytes()) {
        return Vec::new();
    }
    at_constructs(text)
        .unwrap_or_default()
        .into_iter()
        .filter_map(|construct| match construct {
            AtConstruct::Bare { name, start } => Some((name, start)),
            AtConstruct::Sql { .. } | AtConstruct::Python { .. } => None,
        })
        .collect()
}

/// Whether an `@` followed by a name and `(` that is not a kind prefix or declaration occurs.
fn may_hold_bare_call(bytes: &[u8]) -> bool {
    for at in memchr::memchr_iter(b'@', bytes) {
        let start: usize = at + 1;
        let mut end: usize = start;
        while bytes.get(end).is_some_and(|byte| {
            byte.is_ascii_alphanumeric() || *byte == b'_' || *byte >= NON_ASCII_BYTE
        }) {
            end += 1;
        }
        if end == start || bytes[start].is_ascii_digit() {
            continue;
        }
        if matches!(
            &bytes[start..end],
            b"py" | b"sql" | b"const" | b"enum" | b"param"
        ) {
            continue;
        }
        if bytes.get(end) == Some(&b'(') {
            return true;
        }
    }
    false
}
