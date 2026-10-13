//! Text reads, atomic writes, template copies and directory walks.

use std::fs;
use std::path::{Path, PathBuf};
use std::process;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::workspace::constants::{PYTHON_TEMPLATE_SUFFIX, TEMPLATE_SUFFIX};
use crate::workspace::errors::WorkspaceError;

static TEMPORARY_COUNTER: AtomicU64 = AtomicU64::new(0);

/// `path.read_text(encoding="utf-8")`.
pub(crate) fn read_text(path: &Path) -> Result<String, WorkspaceError> {
    let bytes: Vec<u8> = fs::read(path)?;
    match String::from_utf8(bytes) {
        Ok(text) => Ok(text),
        Err(error) => {
            let utf8: std::str::Utf8Error = error.utf8_error();
            Err(WorkspaceError::Decode {
                path: path.to_path_buf(),
                bytes: error.into_bytes(),
                error: utf8,
            })
        }
    }
}

/// Replace `path` with `content` through a temporary sibling file.
pub(crate) fn write_atomically(path: &Path, content: &str) -> Result<(), WorkspaceError> {
    let parent: &Path = path.parent().unwrap_or_else(|| Path::new(""));
    fs::create_dir_all(parent)?;
    let name: String = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let temporary: PathBuf = parent.join(format!(
        ".{name}.{}.{}",
        process::id(),
        TEMPORARY_COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    fs::write(&temporary, content)?;
    fs::rename(&temporary, path)?;
    Ok(())
}

/// The file name a template entry is written as: `.py.txt` loses `.txt`.
fn generated_name(name: &str) -> &str {
    if name.ends_with(PYTHON_TEMPLATE_SUFFIX) {
        return &name[..name.len() - TEMPLATE_SUFFIX.len()];
    }
    name
}

/// Copy the template entries of `source` into the existing directory `target`.
pub(crate) fn copy_entries(source: &Path, target: &Path) -> Result<(), WorkspaceError> {
    for entry in fs::read_dir(source)? {
        let entry: fs::DirEntry = entry?;
        let name: String = entry.file_name().to_string_lossy().into_owned();
        let destination: PathBuf = target.join(generated_name(&name));
        if entry.path().is_dir() {
            fs::create_dir(&destination)?;
            copy_entries(&entry.path(), &destination)?;
        } else {
            fs::write(&destination, fs::read(entry.path())?)?;
        }
    }
    Ok(())
}

/// `_copy_tree`: create `target` (and its parents) and copy the template into it.
pub(crate) fn copy_tree(source: &Path, target: &Path) -> Result<(), WorkspaceError> {
    if target.exists() {
        return Err(WorkspaceError::Io(std::io::Error::from(
            std::io::ErrorKind::AlreadyExists,
        )));
    }
    fs::create_dir_all(target)?;
    copy_entries(source, target)
}

/// Every entry below `root`, without following directory symlinks.
pub(crate) fn walk(root: &Path) -> Vec<PathBuf> {
    let mut found: Vec<PathBuf> = Vec::new();
    let Ok(entries) = fs::read_dir(root) else {
        return found;
    };
    for entry in entries.flatten() {
        let path: PathBuf = entry.path();
        let is_directory: bool = entry.file_type().is_ok_and(|kind| kind.is_dir());
        found.push(path.clone());
        if is_directory {
            found.extend(walk(&path));
        }
    }
    found
}
