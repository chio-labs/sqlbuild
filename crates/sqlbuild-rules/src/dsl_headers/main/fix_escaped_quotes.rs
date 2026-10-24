//! `fix_escaped_quotes`: descriptions escaping or doubling quotes rewritten as `"""` strings.

use crate::dsl_headers::_helpers::quote_fix::header_fixes;
use crate::dsl_headers::_helpers::text::{line_starts, position};
use crate::dsl_headers::main::scan_headers::scan_headers;

/// `text` with each description escaping or doubling quotes rewritten as `"""..."""`, and lines.
pub fn fix_escaped_quotes(text: &[char]) -> (Vec<char>, Vec<usize>) {
    let starts: Vec<usize> = line_starts(text);
    let mut fixes: Vec<(usize, usize, Vec<char>)> = Vec::new();
    for header in scan_headers(text, false) {
        fixes.extend(header_fixes(text, &header));
    }
    let lines: Vec<usize> = fixes
        .iter()
        .map(|(start, _, _)| position(*start, &starts).0)
        .collect();
    let mut fixed: Vec<char> = Vec::with_capacity(text.len());
    let mut cursor: usize = 0;
    for (start, end, rewrite) in fixes {
        fixed.extend(&text[cursor..start]);
        fixed.extend(rewrite);
        cursor = end;
    }
    fixed.extend(&text[cursor..]);
    (fixed, lines)
}
