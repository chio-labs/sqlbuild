//! Python string operations, with offsets in code points as Python's string indexes count them.

/// Python's `str.casefold`.
pub(crate) fn casefold(text: &str) -> String {
    str::to_lowercase(text)
}

/// Python's `str.upper`.
pub(crate) fn upper(text: &str) -> String {
    str::to_uppercase(text)
}

/// `(start, content end, next start)` byte offsets of each line; `\r\n` and `\n` end lines.
fn line_ends(text: &str) -> Vec<(usize, usize, usize)> {
    let mut start: usize = 0;
    text.split_inclusive('\n')
        .map(|line| {
            let content: &str = line.strip_suffix('\n').map_or(line, |content| {
                content.strip_suffix('\r').unwrap_or(content)
            });
            let offsets: (usize, usize, usize) = (start, start + content.len(), start + line.len());
            start += line.len();
            offsets
        })
        .collect()
}

/// The lines of a text and the code-point offset where each starts.
pub(crate) struct LineIndex<'a> {
    pub(crate) lines: Vec<&'a str>,
    /// Code-point offsets of each line start, then the text length.
    pub(crate) starts: Vec<usize>,
}

impl<'a> LineIndex<'a> {
    pub(crate) fn new(text: &'a str) -> Self {
        let ends = line_ends(text);
        let mut starts: Vec<usize> = vec![0];
        let mut lines: Vec<&'a str> = Vec::with_capacity(ends.len());
        for (start, content_end, next_start) in ends {
            lines.push(&text[start..content_end]);
            let previous = starts.last().copied().unwrap_or(0);
            starts.push(previous + text[start..next_start].chars().count());
        }
        Self { lines, starts }
    }

    /// Python's `_line_offset`, clamping the line into the index.
    pub(crate) fn offset(&self, line: i64, column: i64) -> i64 {
        let last: i64 = i64::try_from(self.starts.len()).unwrap_or(i64::MAX) - 1;
        let position: usize = usize::try_from((line - 1).max(0).min(last)).unwrap_or(0);
        i64::try_from(self.starts[position]).unwrap_or(i64::MAX) + column - 1
    }
}

/// Python's `text.count("\n", 0, end)` with Python's slice clamping.
pub(crate) fn newlines_before(text: &str, end: i64) -> i64 {
    let end: usize = clamp(text, end);
    i64::try_from(
        text.chars()
            .take(end)
            .filter(|character| *character == '\n')
            .count(),
    )
    .unwrap_or(i64::MAX)
}

/// Python's `text.rfind("\n", 0, end)` with Python's slice clamping.
pub(crate) fn last_newline_before(text: &str, end: i64) -> i64 {
    let end: usize = clamp(text, end);
    text.chars()
        .take(end)
        .enumerate()
        .filter(|(_, character)| *character == '\n')
        .last()
        .map_or(-1, |(index, _)| i64::try_from(index).unwrap_or(i64::MAX))
}

/// A Python slice bound over `text`'s code points: negative counts from the end.
fn clamp(text: &str, end: i64) -> usize {
    let length: i64 = i64::try_from(text.chars().count()).unwrap_or(i64::MAX);
    let end: i64 = if end < 0 { (length + end).max(0) } else { end };
    usize::try_from(end.min(length)).unwrap_or(0)
}

/// Python's `text[:end]`.
pub(crate) fn prefix(text: &str, end: i64) -> &str {
    &text[..byte_offset(text, clamp(text, end))]
}

/// The byte offset of code point `index`, or the text length past the end.
pub(crate) fn byte_offset(text: &str, index: usize) -> usize {
    text.char_indices()
        .nth(index)
        .map_or(text.len(), |(byte, _)| byte)
}

/// The code-point offset of byte offset `byte` on a character boundary.
pub(crate) fn code_point_offset(text: &str, byte: usize) -> usize {
    text[..byte].chars().count()
}
