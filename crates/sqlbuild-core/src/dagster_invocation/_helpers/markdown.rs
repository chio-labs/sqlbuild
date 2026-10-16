//! A Markdown code span that shows any text verbatim.

use crate::dagster_invocation::constants::{CODE_SPAN_MARK, CODE_SPAN_PADDED_EDGES};

/// `value` fenced by one more backtick than its longest run, padded at a backtick or space edge.
pub(crate) fn markdown_code_span(value: &str) -> String {
    let mut longest: usize = 0;
    let mut current: usize = 0;
    for character in value.chars() {
        current = if character == CODE_SPAN_MARK {
            current + 1
        } else {
            0
        };
        longest = longest.max(current);
    }
    let delimiter: String = CODE_SPAN_MARK.to_string().repeat(longest + 1);
    let padded: bool =
        value.starts_with(CODE_SPAN_PADDED_EDGES) || value.ends_with(CODE_SPAN_PADDED_EDGES);
    let padding: &str = if padded { " " } else { "" };
    format!("{delimiter}{padding}{value}{padding}{delimiter}")
}
