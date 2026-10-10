use std::ffi::OsStr;

/// The path's exact text: UTF-8 as is, any other name escaped so it still names the same file.
pub fn path_text(path: &OsStr) -> String {
    crate::project_snapshot::_helpers::path_text::path_text(path)
}
