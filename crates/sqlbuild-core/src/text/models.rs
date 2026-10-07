//! Positions in authored text, in both UTF-8 bytes and Python code points.

/// One text position; lines and columns are 1-based and columns count code points.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TextPosition {
    pub byte_offset: usize,
    pub char_offset: usize,
    pub line: usize,
    pub column: usize,
}

/// A half-open range of text.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct TextSpan {
    pub start: TextPosition,
    pub end: TextPosition,
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

    /// The position at a code-point offset (a Python string index), or `None` past the end.
    pub fn position_at_char(&self, char_offset: usize) -> Option<TextPosition> {
        if char_offset > self.char_len {
            return None;
        }
        let line_index = self
            .line_char_starts
            .partition_point(|start| *start <= char_offset)
            - 1;
        let line_start = self.line_byte_starts[line_index];
        let column = char_offset - self.line_char_starts[line_index] + 1;
        let byte_offset = self.text[line_start..]
            .char_indices()
            .nth(column - 1)
            .map_or(self.text.len(), |(offset, _)| line_start + offset);
        Some(TextPosition {
            byte_offset,
            char_offset,
            line: line_index + 1,
            column,
        })
    }

    /// The span between two UTF-8 byte offsets, or `None` when either end is not a position.
    pub fn span_at_bytes(&self, start: usize, end: usize) -> Option<TextSpan> {
        if start > end {
            return None;
        }
        Some(TextSpan {
            start: self.position_at_byte(start)?,
            end: self.position_at_byte(end)?,
        })
    }
}

/// The Python string semantics native text helpers reproduce for one CPython release.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PythonText {
    /// Inclusive code point ranges where `str.isalnum()` is true, in order.
    pub(crate) alnum_ranges: &'static [(u32, u32)],
    pub(crate) cleandoc_margin: CleandocMargin,
}

/// The characters `inspect.cleandoc` strips from line starts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum CleandocMargin {
    /// Python 3.12: `str.lstrip()`, any Python whitespace.
    Whitespace,
    /// Python 3.13 and later: `str.lstrip(' ')`, spaces only.
    Spaces,
}
