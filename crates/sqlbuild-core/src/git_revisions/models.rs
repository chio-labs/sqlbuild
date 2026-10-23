//! The resolved base revision of a `--since` comparison.

use std::path::PathBuf;

/// The merge base of a ref and `HEAD`, and where the project lives in the repository.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GitBase {
    /// The ref as the user gave it, after `@base` resolution.
    pub reference: String,
    /// The full hash of the merge-base commit.
    pub merge_base: String,
    pub repository_root: PathBuf,
    /// The project directory relative to the repository root, with `/` separators, empty at the root.
    pub project_prefix: String,
}
