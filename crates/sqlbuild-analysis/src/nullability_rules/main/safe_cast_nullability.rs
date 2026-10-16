//! The nullability of a SAFE_CAST/TRY_CAST-style conversion.

use crate::assembly::analysis_session::constants::{NULLABLE_NULLABILITY, UNKNOWN_NULLABILITY};

/// Nullable when the converted value is nullable; otherwise unknown, since conversion may fail.
pub fn safe_cast_nullability(arguments: &[&str]) -> &'static str {
    if arguments.first() == Some(&NULLABLE_NULLABILITY) {
        NULLABLE_NULLABILITY
    } else {
        UNKNOWN_NULLABILITY
    }
}
