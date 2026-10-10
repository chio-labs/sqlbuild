//! Stage edits in a scratch copy, then commit with rollback, as `workspace.py` does.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use sqlbuild_core::text::main::decode_python_text::decode_python_text;

use crate::refactoring::_helpers::edits::text_edits::apply_text_edits;
use crate::refactoring::_helpers::files::paths::{join, suffix};
use crate::refactoring::_helpers::scanning::chars::chars;
use crate::refactoring::constants::{
    COPIED_PROJECT_SUFFIXES, HIDDEN_PREFIX, IGNORED_PROJECT_DIRECTORIES, PYCACHE_DIRECTORY,
    WRITE_ERROR_CODE,
};
use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::models::FileChange;
use crate::refactoring::types::Originals;

fn io_error(path: &Path, error: impl std::fmt::Display) -> RefactorError {
    RefactorError {
        kind: RefactorErrorKind::Io,
        code: String::new(),
        message: format!("{}: {error}", path.display()),
        help: None,
    }
}

/// Copy every file compilation can read, skipping build output and hidden directories.
pub(crate) fn copy_project_inputs(
    project_dir: &Path,
    staging_dir: &Path,
) -> Result<usize, RefactorError> {
    copy_directory(project_dir, project_dir, staging_dir)
}

fn copy_directory(root: &Path, current: &Path, staging_dir: &Path) -> Result<usize, RefactorError> {
    let mut entries: Vec<fs::DirEntry> = fs::read_dir(current)
        .map_err(|error| io_error(current, error))?
        .filter_map(Result::ok)
        .collect();
    entries.sort_by_key(fs::DirEntry::file_name);
    let mut copied = 0;
    let mut directories: Vec<PathBuf> = Vec::new();
    for entry in entries {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().into_owned();
        let is_link = entry.file_type().is_ok_and(|kind| kind.is_symlink());
        if path.is_dir() {
            let ignored = name.starts_with(HIDDEN_PREFIX)
                || (current == root && IGNORED_PROJECT_DIRECTORIES.contains(&name.as_str()))
                || name == PYCACHE_DIRECTORY;
            if !ignored && !is_link {
                directories.push(path);
            }
            continue;
        }
        if !COPIED_PROJECT_SUFFIXES.contains(&suffix(&name)) || name.starts_with(HIDDEN_PREFIX) {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .map_err(|error| io_error(&path, error))?;
        let destination = staging_dir.join(relative);
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent).map_err(|error| io_error(parent, error))?;
        }
        fs::copy(&path, &destination).map_err(|error| io_error(&path, error))?;
        copied += 1;
    }
    for directory in directories {
        copied += copy_directory(root, &directory, staging_dir)?;
    }
    Ok(copied)
}

/// `Path.read_text(encoding="utf-8")`: strict UTF-8 with universal newlines.
fn read_text(path: &Path) -> Result<String, RefactorError> {
    let bytes = fs::read(path).map_err(|error| io_error(path, error))?;
    decode_python_text(&bytes).map_err(|_| io_error(path, "'utf-8' codec can't decode the file"))
}

/// The current text of every file a plan changes.
pub(crate) fn read_originals(
    project_dir: &Path,
    changes: &[FileChange],
) -> Result<Originals, RefactorError> {
    let mut originals: Originals = Vec::new();
    for change in changes {
        let text = read_text(&join(project_dir, &change.original_path))?;
        match originals
            .iter_mut()
            .find(|(path, _)| *path == change.original_path)
        {
            Some(entry) => entry.1 = text,
            None => originals.push((change.original_path.clone(), text)),
        }
    }
    Ok(originals)
}

fn original<'a>(originals: &'a Originals, path: &str) -> &'a str {
    originals
        .iter()
        .find(|(item, _)| item == path)
        .map(|(_, text)| text.as_str())
        .unwrap_or_default()
}

/// The new text of every changed file, keyed by its final path.
fn edited_contents(
    originals: &Originals,
    changes: &[FileChange],
) -> Result<Vec<(String, String)>, RefactorError> {
    changes
        .iter()
        .map(|change| {
            let text = chars(original(originals, &change.original_path));
            let edited: String = apply_text_edits(&text, &change.edits)?
                .into_iter()
                .collect();
            Ok((change.path.clone(), edited))
        })
        .collect()
}

fn contents_for<'a>(contents: &'a [(String, String)], path: &str) -> &'a str {
    contents
        .iter()
        .rev()
        .find(|(item, _)| item == path)
        .map(|(_, text)| text.as_str())
        .unwrap_or_default()
}

/// `Path.write_text`: text mode translates line breaks to the platform's.
fn write_text(path: &Path, contents: &str) -> Result<(), RefactorError> {
    let translated = if cfg!(windows) {
        contents.replace('\n', "\r\n")
    } else {
        contents.to_owned()
    };
    fs::write(path, translated).map_err(|error| io_error(path, error))
}

/// Apply a plan to the scratch copy.
pub(crate) fn write_staged_changes(
    staging_dir: &Path,
    originals: &Originals,
    changes: &[FileChange],
) -> Result<(), RefactorError> {
    let contents = edited_contents(originals, changes)?;
    for change in changes.iter().filter(|change| change.moved()) {
        let _ = fs::remove_file(join(staging_dir, &change.original_path));
    }
    for change in changes {
        let target = join(staging_dir, &change.path);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|error| io_error(parent, error))?;
        }
        write_text(&target, contents_for(&contents, &change.path))?;
    }
    prune_emptied_directories(staging_dir, changes);
    Ok(())
}

/// Write a verified plan into the project, restoring every file if any write fails.
pub(crate) fn commit_changes(
    project_dir: &Path,
    originals: &Originals,
    changes: &[FileChange],
) -> Result<Vec<PathBuf>, RefactorError> {
    let current = read_originals(project_dir, changes)?;
    let changed: Vec<String> = changed_paths(originals, &current);
    if !changed.is_empty() || current.len() != originals.len() {
        return Err(RefactorError {
            kind: RefactorErrorKind::Write,
            code: WRITE_ERROR_CODE.to_owned(),
            message: format!(
                "files changed while the refactoring ran: {}",
                changed.join(", ")
            ),
            help: Some("nothing was written; run the command again".to_owned()),
        });
    }
    let contents = edited_contents(originals, changes)?;
    let (progress, result) = write_all(project_dir, changes, &contents);
    if let Err(error) = result {
        rollback(
            project_dir,
            originals,
            &progress.written,
            &progress.created_directories,
        );
        return Err(error);
    }
    prune_emptied_directories(project_dir, changes);
    Ok(progress.written)
}

/// Original paths whose text on disk differs from the planned original, sorted.
fn changed_paths(originals: &Originals, current: &[(String, String)]) -> Vec<String> {
    let mut changed: Vec<String> = originals
        .iter()
        .filter(|(path, text)| current_text(current, path) != Some(text))
        .map(|(path, _)| path.clone())
        .collect();
    changed.sort();
    changed
}

fn current_text<'a>(current: &'a [(String, String)], path: &str) -> Option<&'a String> {
    current
        .iter()
        .find(|(item, _)| item == path)
        .map(|(_, now)| now)
}

/// What a commit wrote before it finished or failed.
#[derive(Default)]
struct WriteProgress {
    created_directories: Vec<PathBuf>,
    written: Vec<PathBuf>,
}

fn write_all(
    project_dir: &Path,
    changes: &[FileChange],
    contents: &[(String, String)],
) -> (WriteProgress, Result<(), RefactorError>) {
    let mut progress = WriteProgress::default();
    let mut write = || -> Result<(), RefactorError> {
        for change in changes {
            let target = join(project_dir, &change.path);
            if let Some(parent) = target.parent() {
                progress
                    .created_directories
                    .extend(missing_directories(parent));
                fs::create_dir_all(parent).map_err(|error| io_error(parent, error))?;
            }
            progress.written.push(target.clone());
            if !target.exists() {
                let source = join(project_dir, &change.original_path);
                fs::copy(&source, &target).map_err(|error| io_error(&source, error))?;
            }
            write_atomically(&target, contents_for(contents, &change.path))?;
        }
        for change in changes.iter().filter(|change| change.moved()) {
            let source = join(project_dir, &change.original_path);
            fs::remove_file(&source).map_err(|error| io_error(&source, error))?;
        }
        Ok(())
    };
    let result = write();
    (progress, result)
}

/// Replace a text file atomically with a temporary file in its folder, keeping its mode.
fn write_atomically(path: &Path, contents: &str) -> Result<(), RefactorError> {
    let directory = path.parent().unwrap_or_else(|| Path::new("."));
    let file_name = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let permissions = fs::metadata(path)
        .map_err(|error| io_error(path, error))?
        .permissions();
    let mut temporary = tempfile::Builder::new()
        .prefix(&format!(".{file_name}."))
        .tempfile_in(directory)
        .map_err(|error| io_error(path, error))?;
    fs::set_permissions(temporary.path(), permissions).map_err(|error| io_error(path, error))?;
    temporary
        .write_all(contents.as_bytes())
        .and_then(|()| temporary.as_file().sync_all())
        .map_err(|error| io_error(path, error))?;
    temporary
        .persist(path)
        .map_err(|error| io_error(path, error.error))?;
    Ok(())
}

/// Remove folders a move left empty, walking up to the root.
pub(crate) fn prune_emptied_directories(root: &Path, changes: &[FileChange]) {
    for change in changes.iter().filter(|change| change.moved()) {
        let mut directory = join(root, &change.original_path);
        directory.pop();
        while directory != root
            && directory.is_dir()
            && fs::read_dir(&directory).is_ok_and(|mut entries| entries.next().is_none())
        {
            if fs::remove_dir(&directory).is_err() {
                break;
            }
            directory.pop();
        }
    }
}

fn rollback(
    project_dir: &Path,
    originals: &Originals,
    written: &[PathBuf],
    created_directories: &[PathBuf],
) {
    let original_paths: Vec<PathBuf> = originals
        .iter()
        .map(|(path, _)| join(project_dir, path))
        .collect();
    for path in written {
        if !original_paths.contains(path) {
            let _ = fs::remove_file(path);
        }
    }
    for (relative, text) in originals {
        let restored = join(project_dir, relative);
        if restored.exists() {
            let _ = write_atomically(&restored, text);
        } else {
            let _ = write_text(&restored, text);
        }
    }
    for directory in created_directories.iter().rev() {
        if directory.is_dir()
            && fs::read_dir(directory).is_ok_and(|mut entries| entries.next().is_none())
        {
            let _ = fs::remove_dir(directory);
        }
    }
}

fn missing_directories(path: &Path) -> Vec<PathBuf> {
    let mut missing: Vec<PathBuf> = Vec::new();
    let mut current = path.to_path_buf();
    while !current.exists() {
        missing.push(current.clone());
        if !current.pop() {
            break;
        }
    }
    missing.reverse();
    missing
}
