//! Python's `reject_cursor_intrinsics` for SQL that it accepts.

use crate::cursor_intrinsics::_helpers::scan::{contains_intrinsic_name, step};
use crate::cursor_intrinsics::models::IntrinsicCheck;

/// `Free` where Python accepts `sql`; anything Python could reject or judge by Unicode defers.
#[must_use]
pub fn intrinsic_free(sql: &str, reserved_markers: &[String]) -> IntrinsicCheck {
    if reserved_markers
        .iter()
        .any(|marker| sql.contains(marker.as_str()))
    {
        return IntrinsicCheck::Deferred;
    }
    let bytes: &[u8] = sql.as_bytes();
    if !contains_intrinsic_name(bytes) {
        return IntrinsicCheck::Free;
    }
    let mut index: usize = 0;
    while index < bytes.len() {
        let Ok(next) = step(bytes, index) else {
            return IntrinsicCheck::Deferred;
        };
        index = next;
    }
    IntrinsicCheck::Free
}
