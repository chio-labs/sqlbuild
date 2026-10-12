//! `reject_cursor_intrinsics`, with the error it raises.

use crate::cursor_intrinsics::main::replace_intrinsics::replace_intrinsics;
use crate::cursor_intrinsics::models::IntrinsicCheck;

/// Accept `sql` free of cursor intrinsics and reserved markers, or return its error for `context`.
#[must_use]
pub fn intrinsic_free(sql: &str, reserved_markers: &[String], context: &str) -> IntrinsicCheck {
    if reserved_markers
        .iter()
        .any(|marker| sql.contains(marker.as_str()))
    {
        return IntrinsicCheck::Rejected(format!(
            "{context} contains a reserved internal cursor marker"
        ));
    }
    match replace_intrinsics(sql, context, str::to_owned) {
        Err(message) => IntrinsicCheck::Rejected(message),
        Ok((_, true)) => IntrinsicCheck::Rejected(format!(
            "{context} uses cursor intrinsics, which are only supported in cursor-based \
             incremental model query SQL"
        )),
        Ok((_, false)) => IntrinsicCheck::Free,
    }
}
