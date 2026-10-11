//! A cleaned SQL-test or scenario body offset mapped to its authored file offset.

use crate::sql_test_attachment::_helpers::authored_offsets::authored_offset;

/// `authored_file_offset`: the file code-point offset of `body_offset`, when it is exact.
#[must_use]
pub fn authored_test_offset(
    contents: &str,
    authored: &str,
    span: Option<(usize, usize)>,
    body_offset: usize,
) -> Option<usize> {
    authored_offset(contents, authored, span, body_offset)
}
