//! `sql_body_ranges`: the SQL bodies around and between a file's headers.

use crate::dsl_headers::_helpers::scan::first_non_whitespace;
use crate::dsl_headers::models::HeaderSpan;

/// Non-empty SQL body ranges around and between the headers.
pub fn sql_body_ranges(text: &[char], headers: &[HeaderSpan]) -> Vec<(usize, usize)> {
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    let mut cursor: usize = 0;
    for header in headers {
        let body_start: usize = first_non_whitespace(text, cursor, header.start);
        if body_start < header.start {
            ranges.push((body_start, header.start));
        }
        cursor = header.end;
    }
    let tail_start: usize = first_non_whitespace(text, cursor, text.len());
    if tail_start < text.len() {
        ranges.push((tail_start, text.len()));
    }
    ranges
}
