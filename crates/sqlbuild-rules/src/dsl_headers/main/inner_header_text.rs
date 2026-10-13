//! `inner_header_text`: the text between a header's parentheses.

/// The text between a header's first `(` and last `)`, or empty.
pub fn inner_header_text(header_text: &[char]) -> &[char] {
    let open: Option<usize> = header_text.iter().position(|character| *character == '(');
    let close: Option<usize> = header_text.iter().rposition(|character| *character == ')');
    match (open, close) {
        (Some(open), Some(close)) if close > open => &header_text[open + 1..close],
        _ => &[],
    }
}
