//! The exit code of `sqb audit`.

/// 1 when any audit failed with error severity, else 0.
#[must_use]
pub fn audit_exit_code(failed: usize) -> i32 {
    i32::from(failed > 0)
}
