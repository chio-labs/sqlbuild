//! Python's `str.splitlines()` with no arguments.

/// Whether Python's `str.splitlines()` ends a line at `character`.
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

/// Python's `text.splitlines()`: lines without their endings; `\r\n` ends one line.
#[must_use]
pub fn python_splitlines(text: &str) -> Vec<&str> {
    let mut lines: Vec<&str> = Vec::new();
    let mut start: usize = 0;
    let mut characters = text.char_indices().peekable();
    while let Some((index, character)) = characters.next() {
        if !is_line_boundary(character) {
            continue;
        }
        lines.push(&text[start..index]);
        start = index + character.len_utf8();
        if character == '\r' && characters.peek().is_some_and(|(_, next)| *next == '\n') {
            let _ = characters.next();
            start += 1;
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}
