//! Staged temporary files and backups of generated skill targets, with rollback.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::errors::{SkillInstallError, SkillInstallErrorKind};

const DEFAULT_MODE: u32 = 0o644;

/// One staged replacement: the temporary content, the backup of the old target, the target.
pub(crate) struct Staged {
    pub(crate) temporary: PathBuf,
    pub(crate) backup: Option<PathBuf>,
    pub(crate) target: PathBuf,
}

pub(crate) fn io_error(error: &std::io::Error) -> SkillInstallError {
    SkillInstallError {
        kind: SkillInstallErrorKind::Io,
        message: error.to_string(),
        notes: Vec::new(),
    }
}

/// Create a new hidden sibling of `target` holding `content`, and return its path.
fn write_sibling(
    target: &Path,
    suffix: &str,
    content: &[u8],
    mode: u32,
) -> std::io::Result<PathBuf> {
    let name: String = target
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let nanos: u128 = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or_default();
    let mut attempt: u32 = 0;
    loop {
        let path: PathBuf = target.with_file_name(format!(
            ".{name}.{}-{nanos}-{attempt}{suffix}",
            std::process::id()
        ));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
        {
            Ok(mut file) => {
                file.write_all(content)?;
                set_mode(&path, mode)?;
                return Ok(path);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => attempt += 1,
            Err(error) => return Err(error),
        }
    }
}

#[cfg(unix)]
fn file_mode(path: &Path) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    fs::metadata(path)
        .map(|metadata| metadata.permissions().mode() & 0o7777)
        .unwrap_or(DEFAULT_MODE)
}

#[cfg(not(unix))]
fn file_mode(_path: &Path) -> u32 {
    DEFAULT_MODE
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> std::io::Result<()> {
    Ok(())
}

fn read_if_file(path: &Path) -> std::io::Result<Option<Vec<u8>>> {
    if path.is_file() {
        return fs::read(path).map(Some);
    }
    Ok(None)
}

/// A temporary copy of `content` beside each target and a backup of each existing target.
pub(crate) fn stage(targets: &[PathBuf], content: &[u8]) -> Result<Vec<Staged>, SkillInstallError> {
    let mut staged: Vec<Staged> = Vec::with_capacity(targets.len());
    let staging = |staged: &mut Vec<Staged>| -> std::io::Result<()> {
        for target in targets {
            if let Some(parent) = target.parent() {
                fs::create_dir_all(parent)?;
            }
            let mode: u32 = if target.is_file() {
                file_mode(target)
            } else {
                DEFAULT_MODE
            };
            let temporary: PathBuf = write_sibling(target, ".tmp", content, mode)?;
            staged.push(Staged {
                temporary,
                backup: None,
                target: target.clone(),
            });
            if target.is_file() {
                let backup: PathBuf = write_sibling(target, ".bak", &fs::read(target)?, mode)?;
                if let Some(last) = staged.last_mut() {
                    last.backup = Some(backup);
                }
            }
        }
        Ok(())
    };
    if let Err(error) = staging(&mut staged) {
        remove_staged(&staged, &[]);
        return Err(io_error(&error));
    }
    Ok(staged)
}

/// Replace each target with its staged content unless it changed since staging.
pub(crate) fn apply(staged: &[Staged], installed: &[u8]) -> Result<(), SkillInstallError> {
    let mut replaced: Vec<(Option<&Path>, &Path)> = Vec::new();
    let mut outcome: Result<(), SkillInstallError> = Ok(());
    for entry in staged {
        let replacing = || -> Result<(), SkillInstallError> {
            let current: Option<Vec<u8>> =
                read_if_file(&entry.target).map_err(|error| io_error(&error))?;
            let expected: Option<Vec<u8>> = match &entry.backup {
                Some(backup) => Some(fs::read(backup).map_err(|error| io_error(&error))?),
                None => None,
            };
            if current != expected {
                return Err(SkillInstallError {
                    kind: SkillInstallErrorKind::Refused,
                    message: format!(
                        "refusing to overwrite rules skill changed during installation: {}",
                        entry.target.display()
                    ),
                    notes: Vec::new(),
                });
            }
            fs::rename(&entry.temporary, &entry.target).map_err(|error| io_error(&error))
        };
        if let Err(error) = replacing() {
            outcome = Err(error);
            break;
        }
        replaced.push((entry.backup.as_deref(), &entry.target));
    }
    let mut retained: Vec<PathBuf> = Vec::new();
    if let Err(error) = &mut outcome {
        let (kept, notes) = rollback(&replaced, installed);
        retained = kept;
        error.notes.extend(notes);
    }
    remove_staged(staged, &retained);
    outcome
}

/// Restore replaced targets; returns the backups kept for recovery and the rollback notes.
fn rollback(replaced: &[(Option<&Path>, &Path)], installed: &[u8]) -> (Vec<PathBuf>, Vec<String>) {
    let mut retained: Vec<PathBuf> = Vec::new();
    let mut notes: Vec<String> = Vec::new();
    let backup_text = |backup: Option<&Path>| {
        backup.map_or_else(|| "None".to_owned(), |path| path.display().to_string())
    };
    for (backup, target) in replaced.iter().rev() {
        let restoring = || -> std::io::Result<bool> {
            if read_if_file(target)?.as_deref() != Some(installed) {
                return Ok(false);
            }
            match backup {
                None => match fs::remove_file(target) {
                    Err(error) if error.kind() != std::io::ErrorKind::NotFound => Err(error),
                    _ => Ok(true),
                },
                Some(backup) => fs::rename(backup, target).map(|()| true),
            }
        };
        match restoring() {
            Ok(true) => {}
            Ok(false) => {
                retained.extend(backup.map(Path::to_path_buf));
                notes.push(format!(
                    "rollback preserved concurrently changed target {}; recovery backup: {}",
                    target.display(),
                    backup_text(*backup)
                ));
            }
            Err(error) => {
                retained.extend(backup.map(Path::to_path_buf));
                notes.push(format!(
                    "rollback failed for {}: {error}; recovery backup: {}",
                    target.display(),
                    backup_text(*backup)
                ));
            }
        }
    }
    (retained, notes)
}

fn remove_staged(staged: &[Staged], retained: &[PathBuf]) {
    for entry in staged {
        let _ = fs::remove_file(&entry.temporary);
        if let Some(backup) = &entry.backup
            && !retained.contains(backup)
        {
            let _ = fs::remove_file(backup);
        }
    }
}
