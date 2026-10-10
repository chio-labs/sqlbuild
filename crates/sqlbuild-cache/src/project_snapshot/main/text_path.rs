use std::path::PathBuf;

/// The path `path_text` produced `text` for.
pub fn text_path(text: &str) -> PathBuf {
    crate::project_snapshot::_helpers::path_text::text_path(text)
}
