//! Positions in authored text, in both UTF-8 bytes and Python code points.

/// One text position; lines and columns are 1-based and columns count code points.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TextPosition {
    pub byte_offset: usize,
    pub char_offset: usize,
    pub line: usize,
    pub column: usize,
}

/// Line starts of one text, converting offsets into Python-compatible lines and columns.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineIndex<'text> {
    text: &'text str,
    line_byte_starts: Vec<usize>,
    line_char_starts: Vec<usize>,
    char_len: usize,
}

impl<'text> LineIndex<'text> {
    /// Index the line starts of `text`; only `\n` ends a line, as in Python's `str.count`.
    pub fn new(text: &'text str) -> Self {
        let mut line_byte_starts = vec![0];
        let mut line_char_starts = vec![0];
        let mut char_len = 0;
        for (byte_offset, character) in text.char_indices() {
            char_len += 1;
            if character == '\n' {
                line_byte_starts.push(byte_offset + 1);
                line_char_starts.push(char_len);
            }
        }
        Self {
            text,
            line_byte_starts,
            line_char_starts,
            char_len,
        }
    }

    /// The position at a UTF-8 byte offset, or `None` past the end or inside a character.
    pub fn position_at_byte(&self, byte_offset: usize) -> Option<TextPosition> {
        if byte_offset > self.text.len() || !self.text.is_char_boundary(byte_offset) {
            return None;
        }
        let line_index = self
            .line_byte_starts
            .partition_point(|start| *start <= byte_offset)
            - 1;
        let line_start = self.line_byte_starts[line_index];
        let column = self.text[line_start..byte_offset].chars().count() + 1;
        Some(TextPosition {
            byte_offset,
            char_offset: self.line_char_starts[line_index] + column - 1,
            line: line_index + 1,
            column,
        })
    }
}
