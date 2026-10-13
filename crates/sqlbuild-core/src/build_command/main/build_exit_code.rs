//! The build exit code.

/// `0` only when the build succeeded and no Python node or check failed.
#[must_use]
pub fn build_exit_code(succeeded: bool, (python_failed, checks_failed): (bool, bool)) -> i32 {
    i32::from(!succeeded || python_failed || checks_failed)
}
