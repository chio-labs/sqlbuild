//! The line starts of a source whose newlines are already translated.

use crate::cpython_tree::models::SourceLines;

/// Where each `\n`-terminated line of `source` starts.
pub(crate) fn source_lines(source: &str) -> SourceLines {
    let mut starts: Vec<usize> = vec![0];
    starts.extend(source.match_indices('\n').map(|(index, _)| index + 1));
    SourceLines { starts }
}
