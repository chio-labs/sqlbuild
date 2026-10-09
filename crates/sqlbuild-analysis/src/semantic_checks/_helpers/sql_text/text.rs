//! Python string operations over ASCII text, where byte offsets equal code-point offsets.

use crate::semantic_checks::models::SemanticDeferral;

/// ASCII text or a deferral, because Python's case folding and regex classes differ beyond it.
pub(crate) fn ascii(text: &str) -> Result<&str, SemanticDeferral> {
    if text.is_ascii() {
        Ok(text)
    } else {
        Err(SemanticDeferral::NonAsciiText)
    }
}

/// ASCII text without the separators Python's `\s` matches and Rust's does not.
pub(crate) fn plain_text(text: &str) -> Result<&str, SemanticDeferral> {
    if ascii(text)?
        .bytes()
        .any(|byte| (0x1c..=0x1f).contains(&byte))
    {
        return Err(SemanticDeferral::NonAsciiText);
    }
    Ok(text)
}

/// Python's `str.casefold` on ASCII text.
pub(crate) fn casefold(text: &str) -> String {
    text.to_ascii_lowercase()
}

/// Python's `str.splitlines(keepends=True)` line lengths on ASCII text.
fn line_ends(text: &str) -> Vec<(usize, usize)> {
    let bytes = text.as_bytes();
    let mut lines: Vec<(usize, usize)> = Vec::new();
    let mut start: usize = 0;
    let mut index: usize = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        if matches!(byte, b'\n' | b'\r' | 0x0b | 0x0c | 0x1c | 0x1d | 0x1e) {
            let content_end = index;
            index += 1;
            if byte == b'\r' && bytes.get(index) == Some(&b'\n') {
                index += 1;
            }
            lines.push((start, content_end));
            start = index;
        } else {
            index += 1;
        }
    }
    if start < bytes.len() {
        lines.push((start, bytes.len()));
    }
    lines
}

/// Python's `_line_index`: `splitlines()` and the running starts of `splitlines(keepends=True)`.
pub(crate) struct LineIndex<'a> {
    pub(crate) lines: Vec<&'a str>,
    pub(crate) starts: Vec<usize>,
}

impl<'a> LineIndex<'a> {
    pub(crate) fn new(text: &'a str) -> Self {
        let ends = line_ends(text);
        let mut starts: Vec<usize> = vec![0];
        let mut lines: Vec<&'a str> = Vec::with_capacity(ends.len());
        for (index, (start, content_end)) in ends.iter().enumerate() {
            lines.push(&text[*start..*content_end]);
            let next_start = ends.get(index + 1).map_or(text.len(), |(next, _)| *next);
            let previous = starts.last().copied().unwrap_or(0);
            starts.push(previous + (next_start - start));
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
        text.as_bytes()[..end]
            .iter()
            .filter(|byte| **byte == b'\n')
            .count(),
    )
    .unwrap_or(i64::MAX)
}

/// Python's `text.rfind("\n", 0, end)` with Python's slice clamping.
pub(crate) fn last_newline_before(text: &str, end: i64) -> i64 {
    let end: usize = clamp(text, end);
    text.as_bytes()[..end]
        .iter()
        .rposition(|byte| *byte == b'\n')
        .map_or(-1, |index| i64::try_from(index).unwrap_or(i64::MAX))
}

fn clamp(text: &str, end: i64) -> usize {
    let length: i64 = i64::try_from(text.len()).unwrap_or(i64::MAX);
    let end: i64 = if end < 0 { (length + end).max(0) } else { end };
    usize::try_from(end.min(length)).unwrap_or(0)
}

/// Python's `text[:end]` for a non-negative end on ASCII text.
pub(crate) fn prefix(text: &str, end: i64) -> &str {
    &text[..clamp(text, end)]
}
