//! Cursor intrinsic replacement that reports where each call moved.

use crate::cursor_intrinsics::_helpers::replacement::replaced_with_spans;
use crate::cursor_intrinsics::models::IntrinsicSpan;

/// `sql` with each cursor intrinsic call replaced and each call's byte span, or the call's error.
pub fn replace_intrinsics_with_spans(
    sql: &str,
    context: &str,
    replacement: impl Fn(&str) -> String,
) -> Result<(String, Vec<IntrinsicSpan>), String> {
    replaced_with_spans(sql, context, replacement)
}
