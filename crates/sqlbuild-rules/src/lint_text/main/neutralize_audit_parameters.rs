//! `neutralize_audit_parameters`: unbound generic-audit `@name` arguments replaced by sentinels.

use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::lint_text::_helpers::sites::{ByteSite, assemble, sentinel};
use crate::lint_text::constants::AUDIT_PARAMETER_SENTINEL_PREFIX;
use crate::lint_text::models::Neutralized;

/// Replace `@'name'` and `@name` parameters, but not calls or `@@`, with generated sentinels.
pub fn neutralize_audit_parameters(body: &str) -> Neutralized {
    let bytes: &[u8] = body.as_bytes();
    let mut matches: Vec<(usize, usize, bool)> = Vec::new();
    for (start, byte) in bytes.iter().enumerate() {
        if *byte != b'@' || start > 0 && bytes[start - 1] == b'@' {
            continue;
        }
        if bytes.get(start + 1) == Some(&b'\'') {
            let end: usize = ascii_name_end(bytes, start + 2);
            if end > start + 2 && bytes.get(end) == Some(&b'\'') {
                matches.push((start, end + 1, true));
            }
            continue;
        }
        let end: usize = ascii_name_end(bytes, start + 1);
        if end > start + 1 && !opens_call(body, end) {
            matches.push((start, end, false));
        }
    }
    let byte_sites: Vec<ByteSite> = matches
        .into_iter()
        .enumerate()
        .map(|(index, (start, end, quoted))| {
            let identifier: String = sentinel(AUDIT_PARAMETER_SENTINEL_PREFIX, index);
            let replacement: String = if quoted {
                format!("'{identifier}'")
            } else {
                identifier
            };
            (start, end, replacement)
        })
        .collect();
    assemble(body, byte_sites)
}

/// End of an ASCII `[A-Za-z_][A-Za-z0-9_]*` name at `start`, or `start` when none begins there.
fn ascii_name_end(bytes: &[u8], start: usize) -> usize {
    match bytes.get(start) {
        Some(byte) if byte.is_ascii_alphabetic() || *byte == b'_' => {}
        _ => return start,
    }
    let mut end: usize = start + 1;
    while bytes
        .get(end)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        end += 1;
    }
    end
}

fn opens_call(body: &str, end: usize) -> bool {
    body[end..]
        .chars()
        .find(|character| !python_isspace(*character))
        == Some('(')
}
