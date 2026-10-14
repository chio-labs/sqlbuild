//! Whether only the first DSL header of a file is lintable.

use crate::lint_text::constants::{
    DECLARATION_GROUP_DIRECTORY, MODELS_DIRECTORY, SCOPED_DECLARATION_DIRECTORIES,
};

/// Model files outside declaration folders hold one header; every other file may hold several.
#[must_use]
pub fn first_header_only(relative_parts: &[String]) -> bool {
    let Some((first, rest)) = relative_parts.split_first() else {
        return false;
    };
    let folders: &[String] = rest.split_last().map_or(&[], |(_, folders)| folders);
    first == MODELS_DIRECTORY
        && !folders.iter().any(|folder| {
            folder == DECLARATION_GROUP_DIRECTORY
                || SCOPED_DECLARATION_DIRECTORIES.contains(&folder.as_str())
        })
}
