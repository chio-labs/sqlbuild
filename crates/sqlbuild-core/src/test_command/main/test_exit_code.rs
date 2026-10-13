//! The exit code of `sqb test`.

/// 1 when any test did not pass, else 0.
#[must_use]
pub fn test_exit_code(passed: usize, total: usize) -> i32 {
    i32::from(passed != total)
}
