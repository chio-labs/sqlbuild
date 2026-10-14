//! Where a function's executed SQL is written under `target/run`.

use crate::target_paths::_helpers::path_text::with_suffix;
use crate::target_paths::constants::{FUNCTIONS_DIR, SQL_FILE_SUFFIX};

/// The function's path under `functions/<language>/`, with a `.sql` suffix.
#[must_use]
pub fn function_run_path(relative_path: &str, language: &str) -> String {
    let mut parts = relative_path.split('/');
    let path: String = if parts.next() == Some(FUNCTIONS_DIR) && parts.next() == Some(language) {
        relative_path.to_owned()
    } else {
        format!("{FUNCTIONS_DIR}/{language}/{relative_path}")
    };
    with_suffix(&path, SQL_FILE_SUFFIX)
}
