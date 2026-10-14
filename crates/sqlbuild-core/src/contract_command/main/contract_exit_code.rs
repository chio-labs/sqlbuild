//! The exit code of `sqb contract`.

/// 1 when any difference remains, else 0.
#[must_use]
pub fn contract_exit_code(differences: usize) -> i32 {
    i32::from(differences > 0)
}
