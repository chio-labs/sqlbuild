//! CPython's `lineno` and `col_offset` for a byte offset.

use ruff_text_size::TextSize;

use crate::cpython_tree::models::SourceLines;

/// The 1-based line and the UTF-8 byte column of `offset`, as CPython reports a node start.
pub(crate) fn source_position(lines: &SourceLines, offset: TextSize) -> (usize, usize) {
    let offset: usize = offset.to_usize();
    let line: usize = lines.starts.partition_point(|start| *start <= offset);
    let start: usize = lines
        .starts
        .get(line.saturating_sub(1))
        .copied()
        .unwrap_or_default();
    (line, offset - start)
}
