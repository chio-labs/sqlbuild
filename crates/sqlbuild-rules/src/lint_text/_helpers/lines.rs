//! Python `str.splitlines(keepends=True)` lines with character offsets.

/// One line: its text without the ending, and its character range including the ending.
pub(crate) struct LineSpan<'a> {
    pub(crate) content: &'a str,
    pub(crate) start: usize,
    pub(crate) end: usize,
}

fn is_line_boundary(character: char) -> bool {
    matches!(
        character,
        '\n' | '\r'
            | '\u{0b}'
            | '\u{0c}'
            | '\u{1c}'
            | '\u{1d}'
            | '\u{1e}'
            | '\u{85}'
            | '\u{2028}'
            | '\u{2029}'
    )
}

/// Lines as Python's `splitlines` finds them; `\r\n` ends one line.
pub(crate) fn line_spans(text: &str) -> Vec<LineSpan<'_>> {
    let mut spans: Vec<LineSpan<'_>> = Vec::new();
    let mut byte_start: usize = 0;
    let mut char_start: usize = 0;
    let mut position: usize = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        position += 1;
        if !is_line_boundary(character) {
            continue;
        }
        let content: &str = &text[byte_start..index];
        byte_start = index + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            let _ = characters.next();
            byte_start += 1;
            position += 1;
        }
        spans.push(LineSpan {
            content,
            start: char_start,
            end: position,
        });
        char_start = position;
    }
    if byte_start < text.len() {
        spans.push(LineSpan {
            content: &text[byte_start..],
            start: char_start,
            end: position,
        });
    }
    spans
}
