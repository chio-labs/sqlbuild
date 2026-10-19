//! `store_location_problem`: why a store could not be written, judged from file permissions alone.

use std::path::Path;

/// Why `path` cannot be created or written, from permission bits only, so it never waits on a lock.
#[must_use]
pub fn store_location_problem(path: &Path) -> Option<String> {
    let directory: &Path = path
        .ancestors()
        .skip(1)
        .find(|ancestor| ancestor.is_dir())?;
    let directory_readonly: bool =
        std::fs::metadata(directory).is_ok_and(|metadata| metadata.permissions().readonly());
    if directory_readonly {
        return Some(format!("{} is not writable", directory.display()));
    }
    let file_readonly: bool =
        std::fs::metadata(path).is_ok_and(|metadata| metadata.permissions().readonly());
    file_readonly.then(|| format!("{} is read-only", path.display()))
}
