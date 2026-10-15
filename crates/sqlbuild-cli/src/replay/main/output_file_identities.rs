//! Identify the regular files standard output and error write to.

use crate::replay::_helpers::console::redirected_output_files;

/// Sorted, distinct device and inode pairs of stdout and stderr when they are regular files.
#[must_use]
pub fn output_file_identities() -> Vec<(u64, u64)> {
    redirected_output_files()
}
