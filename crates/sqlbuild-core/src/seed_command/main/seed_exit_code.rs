//! The exit code of `sqb seed`.

/// 1 when any seed failed, else 0.
#[must_use]
pub fn seed_exit_code(failed: usize) -> i32 {
    i32::from(failed > 0)
}
