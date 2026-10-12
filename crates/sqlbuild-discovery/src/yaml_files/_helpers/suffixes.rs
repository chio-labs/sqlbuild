//! `Path.suffix` and `Path.glob` name matching as Python applies them to listed names.

use sqlbuild_core::text::main::glob_name_match::glob_name_match;

/// Python's `PurePath.suffix` of a file name.
pub(crate) fn python_suffix(name: &str) -> &str {
    match name.rfind('.') {
        Some(index) if index > 0 && index + 1 < name.len() => &name[index..],
        _ => "",
    }
}

/// Whether `name` matches a single-name glob with the platform's default case sensitivity.
pub(crate) fn name_matches(name: &str, pattern: &str) -> bool {
    glob_name_match(name, pattern, cfg!(windows))
}
