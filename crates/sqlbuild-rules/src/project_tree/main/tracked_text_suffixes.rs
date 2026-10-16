//! The file types rules may read, as listed in errors.

use crate::project_tree::constants::TRACKED_TEXT_SUFFIXES;

/// The tracked suffixes in sorted order.
#[must_use]
pub fn tracked_text_suffixes() -> &'static [&'static str] {
    &TRACKED_TEXT_SUFFIXES
}
