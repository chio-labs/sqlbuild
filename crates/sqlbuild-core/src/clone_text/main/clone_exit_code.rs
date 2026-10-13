//! The exit code of `sqb clone`.

use crate::clone_text::models::{CloneItemText, CloneStatusKind};

/// 1 when any item failed, else 0.
#[must_use]
pub fn clone_exit_code(items: &[CloneItemText]) -> i32 {
    i32::from(
        items
            .iter()
            .any(|item| item.status == CloneStatusKind::Failed),
    )
}
