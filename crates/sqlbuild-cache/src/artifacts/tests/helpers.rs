use std::path::{Path, PathBuf};

/// `count` distinct SQL artifacts spread over nested directories under `root`.
pub(crate) fn batch(root: &Path, count: usize) -> Vec<(PathBuf, Vec<u8>)> {
    (0..count)
        .map(|index| {
            (
                root.join(format!("group_{}/nested/model_{index}.sql", index % 7)),
                format!("select {index}\n").into_bytes(),
            )
        })
        .collect()
}

/// Create `path` with `contents`, including its parent directories.
pub(crate) fn place(path: &Path, contents: &[u8]) {
    std::fs::create_dir_all(path.parent().expect("artifact parent")).expect("artifact directory");
    std::fs::write(path, contents).expect("existing artifact");
}

/// Every file below `root` as a sorted relative path.
pub(crate) fn tree_files(root: &Path) -> Vec<String> {
    let mut files: Vec<String> = walkdir::WalkDir::new(root)
        .into_iter()
        .flatten()
        .filter(|entry| entry.file_type().is_file())
        .filter_map(|entry| {
            entry
                .path()
                .strip_prefix(root)
                .ok()
                .map(|relative| relative.to_string_lossy().into_owned())
        })
        .collect();
    files.sort();
    files
}
