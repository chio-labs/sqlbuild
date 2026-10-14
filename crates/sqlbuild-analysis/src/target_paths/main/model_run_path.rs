//! Where a model's executed SQL is written under `target/run`.

use crate::target_paths::constants::MODELS_DIR;

/// The model's relative path, under `models/` unless it already starts there.
#[must_use]
pub fn model_run_path(relative_path: &str) -> String {
    if relative_path.split('/').next() == Some(MODELS_DIR) {
        return relative_path.to_owned();
    }
    format!("{MODELS_DIR}/{relative_path}")
}
