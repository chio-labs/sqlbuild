//! A model's name: Python's `Path.stem` of its `/`-separated relative path.

use crate::declarations::_helpers::paths::stem;

/// Python's `PurePath(relative_path).stem` for a `/`-separated relative path.
#[must_use]
pub fn model_file_stem(relative_path: &str) -> &str {
    stem(relative_path.rsplit('/').next().unwrap_or(relative_path))
}
