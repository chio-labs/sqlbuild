//! `_transform_cursor_intrinsics`: replace every intrinsic call, or raise its error.

use crate::cursor_intrinsics::_helpers::replacement::replaced_with_spans;

/// `sql` with each cursor intrinsic call replaced and whether any was, or the malformed-call error.
pub fn replace_intrinsics(
    sql: &str,
    context: &str,
    replacement: impl Fn(&str) -> String,
) -> Result<(String, bool), String> {
    replaced_with_spans(sql, context, replacement)
        .map(|(replaced, spans)| (replaced, !spans.is_empty()))
}
