//! The exit code of `sqb load`.

use crate::load_command::models::LoadCounts;

/// 1 when any load failed, else 0.
#[must_use]
pub fn load_exit_code(counts: LoadCounts) -> i32 {
    i32::from(counts.fail != 0)
}
