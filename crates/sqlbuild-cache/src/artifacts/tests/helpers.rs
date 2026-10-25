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

/// A compiled folder that is a plain directory.
pub(crate) fn plain_compiled_root(target: &Path) {
    std::fs::create_dir_all(target.join("compiled")).expect("compiled folder");
}

/// A compiled folder that is a link to a directory elsewhere in the target folder.
#[cfg(unix)]
pub(crate) fn linked_compiled_root(target: &Path) {
    std::fs::create_dir_all(target.join("elsewhere")).expect("linked folder");
    std::os::unix::fs::symlink(target.join("elsewhere"), target.join("compiled")).expect("link");
}

/// Move `root/t.sql`'s mtime five seconds ahead without changing its bytes.
pub(crate) fn bump_mtime(root: &Path) {
    let file = std::fs::File::options()
        .write(true)
        .open(root.join("t.sql"))
        .expect("artifact");
    let later = std::time::SystemTime::now() + std::time::Duration::from_secs(5);
    file.set_modified(later).expect("mtime");
}
