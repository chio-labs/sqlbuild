//! Where a SQL-test helper problem is reported: its call, else its CTE header, else the block.

use crate::sql_test_attachment::_helpers::text_matching::{cte_header, literal_from};
use crate::sql_test_attachment::models::CteLocation;

/// The code-point index of `needle` in `haystack`, as `str.find` returns it.
fn char_find(haystack: &str, needle: &str) -> Option<usize> {
    haystack
        .find(needle)
        .map(|byte| haystack[..byte].chars().count())
}

/// Line and column of a code-point offset, as `reference_call_location` counts them.
fn line_column(text: &[char], offset: usize) -> (usize, usize) {
    let before: &[char] = &text[..offset.min(text.len())];
    let line: usize = before
        .iter()
        .filter(|character| **character == '\n')
        .count()
        + 1;
    let line_start: usize = before
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(0, |newline| newline + 1);
    (line, offset - line_start + 1)
}

/// `sql_test_cte_location`: the span of `call` inside the CTE, the CTE name, or the block start.
#[must_use]
pub fn sql_test_cte_location(
    contents: &str,
    sql_body: &str,
    cte_name: &str,
    call: Option<&str>,
) -> CteLocation {
    let text: Vec<char> = contents.chars().collect();
    let name: Vec<char> = cte_name.chars().collect();
    let block_offset: usize = char_find(contents, sql_body).unwrap_or(0);
    let header: Option<(usize, usize)> = cte_header(&text, block_offset, &name);
    let (mut start, mut length) =
        header.map_or((block_offset, 0), |(start, _)| (start, name.len()));
    if let (Some(call), Some((_, header_end))) = (call, header) {
        let literal: Vec<char> = call.chars().collect();
        if let Some(found) = literal_from(&text, header_end, &literal) {
            (start, length) = (found, literal.len());
        }
    }
    let (line, column) = line_column(&text, start);
    let (end_line, end_column) = line_column(&text, start + length);
    CteLocation {
        line,
        column,
        end_line,
        end_column,
    }
}
