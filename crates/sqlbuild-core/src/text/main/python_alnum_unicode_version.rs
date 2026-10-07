//! The Unicode version of the native `str.isalnum()` table.

use crate::text::_helpers::alnum_ranges::PYTHON_ALNUM_UNICODE_VERSION;

/// The Unicode version of the Python whose `str.isalnum()` the native table reproduces.
pub fn python_alnum_unicode_version() -> &'static str {
    PYTHON_ALNUM_UNICODE_VERSION
}
