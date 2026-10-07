//! Whether a file lives in a scoped declaration tree rather than a resource tree.

use crate::constants::{
    CANONICAL_AUTHORED_ROOTS, DECLARATION_GROUP_DIRECTORY, MACRO_TESTS_DIRECTORY,
    SCOPED_DECLARATION_DIRECTORIES, SQL_FILE_SUFFIX, SQL_TESTS_ROOT,
};

/// Python's `is_in_scoped_declaration_tree` for a `/`-separated project-relative file path.
pub(crate) fn is_in_scoped_declaration_tree(relative_path: &str) -> bool {
    let parts: Vec<&str> = relative_path.split('/').collect();
    let Some((file_name, directory)) = parts.split_last() else {
        return false;
    };
    let sql_file = has_sql_suffix(file_name);
    for root in CANONICAL_AUTHORED_ROOTS {
        if !directory.starts_with(root) {
            continue;
        }
        let scoped = &directory[root.len()..];
        if root == SQL_TESTS_ROOT && sql_file && scoped.first() == Some(&MACRO_TESTS_DIRECTORY) {
            return false;
        }
        return scoped.iter().any(|component| {
            *component == DECLARATION_GROUP_DIRECTORY
                || SCOPED_DECLARATION_DIRECTORIES.contains(component)
        });
    }
    false
}

/// Python's `Path.suffix == ".sql"`: the last dot starts a suffix unless the name starts with it.
fn has_sql_suffix(file_name: &str) -> bool {
    match file_name.rfind('.') {
        Some(index) if index > 0 && index + 1 < file_name.len() => {
            &file_name[index..] == SQL_FILE_SUFFIX
        }
        _ => false,
    }
}
