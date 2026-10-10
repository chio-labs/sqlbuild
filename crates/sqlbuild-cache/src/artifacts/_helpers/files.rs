//! File operations with Python's `target_writer` semantics.

use std::collections::HashSet;
use std::fs::{File, OpenOptions};
use std::io::{ErrorKind, Read, Write};
use std::path::{Path, PathBuf};

use crate::artifacts::constants::NEW_FILE_MODE;
use crate::artifacts::errors::ArtifactError;
use crate::artifacts::models::{Publication, WrittenArtifacts};

fn io_error(path: &Path) -> impl FnOnce(std::io::Error) -> ArtifactError + '_ {
    move |error| ArtifactError::Io {
        path: path.to_path_buf(),
        error,
    }
}

pub(crate) fn write_artifacts(
    files: &[(PathBuf, Vec<u8>)],
    check_existing: bool,
) -> Result<WrittenArtifacts, ArtifactError> {
    let mut outcome: WrittenArtifacts = WrittenArtifacts::default();
    for (path, contents) in files {
        if check_existing && let Some(existing) = read_regular_file(path)? {
            if existing == *contents {
                outcome.unchanged += 1;
                continue;
            }
            if std::str::from_utf8(&existing).is_err() {
                return Err(ArtifactError::ExistingNotUtf8 { path: path.clone() });
            }
        }
        overwrite_creating_parent(path, contents)?;
        outcome.written += 1;
    }
    Ok(outcome)
}

/// A regular file's bytes, or `None` when nothing comparable is at `path`.
fn read_regular_file(path: &Path) -> Result<Option<Vec<u8>>, ArtifactError> {
    let mut file: File = match File::open(path) {
        Ok(file) => file,
        Err(error) if absent(&error) => return Ok(None),
        Err(error) => return Err(io_error(path)(error)),
    };
    if !file.metadata().map_err(io_error(path))?.is_file() {
        return Ok(None);
    }
    let mut bytes: Vec<u8> = Vec::new();
    match file.read_to_end(&mut bytes) {
        Ok(_) => Ok(Some(bytes)),
        Err(error) if error.kind() == ErrorKind::IsADirectory => Ok(None),
        Err(error) => Err(io_error(path)(error)),
    }
}

fn absent(error: &std::io::Error) -> bool {
    matches!(
        error.kind(),
        ErrorKind::NotFound | ErrorKind::NotADirectory | ErrorKind::IsADirectory
    )
}

fn overwrite_creating_parent(path: &Path, contents: &[u8]) -> Result<(), ArtifactError> {
    match overwrite(path, contents) {
        Err(error) if error.kind() == ErrorKind::NotFound => {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).map_err(io_error(parent))?;
            }
            overwrite(path, contents).map_err(io_error(path))
        }
        result => result.map_err(io_error(path)),
    }
}

fn overwrite(path: &Path, contents: &[u8]) -> std::io::Result<()> {
    let mut file: File = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(path)?;
    file.write_all(contents)
}

/// Delete unmanaged files under `compiled_dir`, then every directory left empty.
pub(crate) fn remove_stale(
    compiled_dir: &Path,
    managed: &HashSet<PathBuf>,
) -> Result<usize, ArtifactError> {
    if !compiled_dir.is_dir() {
        return Ok(0);
    }
    let (_, removed) = remove_stale_under(compiled_dir, managed)?;
    let _ = std::fs::remove_dir(compiled_dir);
    Ok(removed)
}

/// Clean one directory bottom-up as `os.walk(topdown=False)`; returns (gone, files removed).
fn remove_stale_under(
    directory: &Path,
    managed: &HashSet<PathBuf>,
) -> Result<(bool, usize), ArtifactError> {
    let entries = match std::fs::read_dir(directory) {
        Ok(entries) => entries,
        Err(_) => return Ok((false, 0)),
    };
    let mut removed: usize = 0;
    let mut kept_file: bool = false;
    let mut subdirectories_removed: bool = true;
    let mut subdirectories: Vec<PathBuf> = Vec::new();
    let mut files: Vec<PathBuf> = Vec::new();
    for entry in entries.flatten() {
        let path: PathBuf = entry.path();
        if is_directory(&path) {
            subdirectories.push(path);
        } else {
            files.push(path);
        }
    }
    for subdirectory in subdirectories {
        if is_link(&subdirectory) {
            subdirectories_removed = false;
            continue;
        }
        let (gone, below) = remove_stale_under(&subdirectory, managed)?;
        removed += below;
        subdirectories_removed &= gone;
    }
    for file in files {
        if managed.contains(&file) {
            kept_file = true;
        } else {
            std::fs::remove_file(&file).map_err(io_error(&file))?;
            removed += 1;
        }
    }
    let gone: bool = !kept_file && subdirectories_removed && removed_directory(directory);
    Ok((gone, removed))
}

fn removed_directory(directory: &Path) -> bool {
    match std::fs::remove_dir(directory) {
        Ok(()) => true,
        Err(_) => false,
    }
}

/// Whether `path` is a directory after following links, as `DirEntry.is_dir()` reports.
fn is_directory(path: &Path) -> bool {
    match std::fs::metadata(path) {
        Ok(metadata) => metadata.is_dir(),
        Err(_) => false,
    }
}

fn is_link(path: &Path) -> bool {
    match std::fs::symlink_metadata(path) {
        Ok(metadata) => metadata.file_type().is_symlink(),
        Err(_) => false,
    }
}

/// Every file under `staged_dir` with its path relative to it, as `os.walk` lists them.
pub(crate) fn staged_files(staged_dir: &Path) -> Vec<(PathBuf, PathBuf)> {
    let mut files: Vec<(PathBuf, PathBuf)> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![staged_dir.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let Ok(entries) = std::fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path: PathBuf = entry.path();
            if !is_directory(&path) {
                let relative: PathBuf = path
                    .strip_prefix(staged_dir)
                    .map_or_else(|_| path.clone(), Path::to_path_buf);
                files.push((path, relative));
            } else if !is_link(&path) {
                pending.push(path);
            }
        }
    }
    files
}

pub(crate) fn publish_staged(
    staged_dir: &Path,
    compiled_dir: &Path,
    expected: &HashSet<PathBuf>,
) -> Result<Publication, ArtifactError> {
    let staged: Vec<(PathBuf, PathBuf)> = staged_files(staged_dir);
    let listed: HashSet<&PathBuf> = staged.iter().map(|(_, relative)| relative).collect();
    if listed.len() != expected.len() || !expected.iter().all(|path| listed.contains(path)) {
        return Ok(Publication::StagedChanged);
    }
    if let Some(target_dir) = compiled_dir.parent() {
        std::fs::create_dir_all(target_dir).map_err(io_error(target_dir))?;
    }
    if !compiled_dir.is_dir()
        && let Ok(()) = std::fs::rename(staged_dir, compiled_dir)
    {
        return Ok(Publication::MovedTree);
    }
    let check_existing: bool = compiled_dir.is_dir();
    let mut published: Vec<(PathBuf, PathBuf)> = Vec::with_capacity(staged.len());
    for (source, relative) in staged {
        let path: PathBuf = compiled_dir.join(&relative);
        publish_file(&source, &path, check_existing)?;
        published.push((source, path));
    }
    Ok(Publication::Files(published))
}

fn publish_file(source: &Path, path: &Path, check_existing: bool) -> Result<(), ArtifactError> {
    if check_existing && path.is_file() {
        let contents: Vec<u8> = std::fs::read(source).map_err(io_error(source))?;
        let existing: Vec<u8> = std::fs::read(path).map_err(io_error(path))?;
        if existing == contents {
            return Ok(());
        }
        if std::str::from_utf8(&existing).is_err() {
            return Err(ArtifactError::ExistingNotUtf8 {
                path: path.to_path_buf(),
            });
        }
        return overwrite(path, &contents).map_err(io_error(path));
    }
    let move_error = |error: std::io::Error| ArtifactError::Move {
        source: source.to_path_buf(),
        path: path.to_path_buf(),
        error,
    };
    match move_new_file(source, path) {
        Err(error) if error.kind() == ErrorKind::NotFound => {
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).map_err(io_error(parent))?;
            }
            move_new_file(source, path).map_err(move_error)
        }
        result => result.map_err(move_error),
    }
}

fn move_new_file(source: &Path, path: &Path) -> std::io::Result<()> {
    match std::fs::rename(source, path) {
        Err(error) if error.kind() == ErrorKind::CrossesDevices => copy_new_file(source, path),
        result => result,
    }
}

/// Copy across filesystems through a sibling temporary file so the new file appears atomically.
fn copy_new_file(source: &Path, path: &Path) -> std::io::Result<()> {
    let directory: &Path = path.parent().unwrap_or_else(|| Path::new("."));
    let mut builder = tempfile::Builder::new();
    let prefix: String = format!(
        ".{}.",
        path.file_name().unwrap_or_default().to_string_lossy()
    );
    let _ = builder.prefix(&prefix).suffix(".tmp");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = builder.permissions(std::fs::Permissions::from_mode(NEW_FILE_MODE));
    }
    let mut temporary = builder.tempfile_in(directory)?;
    temporary.write_all(&std::fs::read(source)?)?;
    temporary
        .persist(path)
        .map(|_| ())
        .map_err(|error| error.error)
}
