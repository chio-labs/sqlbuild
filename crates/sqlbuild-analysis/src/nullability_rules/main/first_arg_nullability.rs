//! The nullability of a null-propagating unary function.

use crate::assembly::analysis_session::constants::UNKNOWN_NULLABILITY;

/// The first argument's nullability, or unknown without arguments.
pub fn first_arg_nullability<'a>(arguments: &[&'a str]) -> &'a str {
    arguments.first().copied().unwrap_or(UNKNOWN_NULLABILITY)
}
