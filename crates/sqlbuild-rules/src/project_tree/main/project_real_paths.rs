use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};

use crate::project_tree::main::project_real_path::project_real_path;

/// `project_real_path` of every path, resolving each shared parent folder once.
pub fn project_real_paths(paths: &[&Path]) -> Vec<PathBuf> {
    let plain: Vec<Option<(&Path, &std::ffi::OsStr)>> =
        paths.iter().map(|path| plain_file(path)).collect();
    let mut folders: HashMap<&Path, Option<PathBuf>> = HashMap::new();
    for (folder, _) in plain.iter().flatten() {
        let _ = folders
            .entry(folder)
            .or_insert_with(|| resolved_folder(folder));
    }
    paths
        .iter()
        .zip(plain)
        .map(|(path, plain)| match plain {
            Some((folder, name)) => match &folders[folder] {
                Some(resolved) => resolved.join(name),
                None => project_real_path(path),
            },
            None => project_real_path(path),
        })
        .collect()
}

/// The folder and last name of `path` when that name is spelled last and is not a link.
fn plain_file(path: &Path) -> Option<(&Path, &std::ffi::OsStr)> {
    if !cfg!(target_os = "linux") {
        return None;
    }
    let (Some(folder), Some(Component::Normal(name))) =
        (path.parent(), path.components().next_back())
    else {
        return None;
    };
    let spelled_last: bool = path
        .as_os_str()
        .as_encoded_bytes()
        .strip_suffix(name.as_encoded_bytes())
        .is_some_and(|rest| rest.ends_with(b"/"));
    if folder.as_os_str().is_empty() || !spelled_last {
        return None;
    }
    match std::fs::symlink_metadata(path) {
        Ok(metadata) if !metadata.file_type().is_symlink() => Some((folder, name)),
        Ok(_link) => None,
        Err(_absent) => None,
    }
}

fn resolved_folder(folder: &Path) -> Option<PathBuf> {
    let Ok(resolved) = std::fs::canonicalize(folder) else {
        return None;
    };
    Some(resolved)
}
