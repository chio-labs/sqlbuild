//! Python's `omitted_ceremonial_select_offset` under an adapter's lexical syntax.

use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::ceremonial_select::_helpers::boundaries::{next_boundary, starts_with_keyword};
use crate::ceremonial_select::_helpers::segments::{
    may_end_with_comment, segment_bounds, trimmed_end,
};
use crate::ceremonial_select::models::OmittedSelect;

/// The offset after the body's last top-level `)` when only a terminator follows its CTEs.
#[must_use]
pub fn omitted_select_offset(sql: &str, syntax: &LexicalSyntax) -> OmittedSelect {
    let bytes: &[u8] = sql.as_bytes();
    let prefixes: &[String] = &syntax.line_comment_prefixes;
    let tail: &[u8] = &bytes[..trimmed_end(bytes, 0, bytes.len())];
    if !tail.ends_with(b")") && !may_end_with_comment(tail, prefixes) {
        return OmittedSelect::Absent;
    }
    let mut bounds: Option<(usize, usize)> = None;
    let mut last_close: Option<usize> = None;
    let mut depth: i64 = 0;
    let mut segment_start: usize = 0;
    let mut index: usize = 0;
    while let Some(boundary) = next_boundary(bytes, index, prefixes) {
        match dialect_non_code_end(bytes, boundary, syntax) {
            Err(_) => return OmittedSelect::Absent,
            Ok(Some(end)) => {
                bounds = segment_bounds(bytes, segment_start, boundary, bounds).or(bounds);
                segment_start = end;
                index = end;
            }
            Ok(None) => {
                if bytes[boundary] == b'(' {
                    depth += 1;
                } else if bytes[boundary] == b')' {
                    depth -= 1;
                    last_close = (depth == 0).then_some(boundary);
                }
                index = boundary + 1;
            }
        }
    }
    bounds = segment_bounds(bytes, segment_start, bytes.len(), bounds).or(bounds);
    let Some((first, last)) = bounds else {
        return OmittedSelect::Absent;
    };
    if Some(last) != last_close {
        return OmittedSelect::Absent;
    }
    if starts_with_keyword(sql, first) {
        OmittedSelect::At(sql[..=last].chars().count())
    } else {
        OmittedSelect::Absent
    }
}
