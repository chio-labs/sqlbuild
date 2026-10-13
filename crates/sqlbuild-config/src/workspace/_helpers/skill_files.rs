//! Packaged skill files and the generated copies installed from them.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use crate::workspace::_helpers::files::{read_text, walk, write_atomically};
use crate::workspace::constants::{
    FRONTMATTER_CLOSING, FRONTMATTER_OPENING, GENERATED_MARKER, LEGACY_GENERATED_MARKER,
    SKILL_ENTRY_FILE, SKILL_FILE_SUFFIX, SKIPPED_SKILL_PREFIXES,
};
use crate::workspace::errors::WorkspaceError;

/// Skill-relative paths and their generated contents, sorted by path.
pub(crate) type SkillFiles = BTreeMap<String, String>;

/// `ensure_generated_marker`.
pub(crate) fn with_marker(content: String) -> String {
    if content.contains(GENERATED_MARKER) {
        return content;
    }
    if content.contains(LEGACY_GENERATED_MARKER) {
        return content.replacen(LEGACY_GENERATED_MARKER, GENERATED_MARKER, 1);
    }
    if content.starts_with(FRONTMATTER_OPENING)
        && let Some(position) = content[FRONTMATTER_OPENING.len()..].find(FRONTMATTER_CLOSING)
    {
        let insert_at: usize = FRONTMATTER_OPENING.len() + position + FRONTMATTER_CLOSING.len();
        return format!(
            "{}\n{GENERATED_MARKER}\n{}",
            &content[..insert_at],
            &content[insert_at..]
        );
    }
    format!("{GENERATED_MARKER}\n{content}")
}

fn collect(node: &Path, prefix: &str) -> Result<SkillFiles, WorkspaceError> {
    let mut files: SkillFiles = SkillFiles::new();
    for entry in fs::read_dir(node)? {
        let entry: fs::DirEntry = entry?;
        let name: String = entry.file_name().to_string_lossy().into_owned();
        if SKIPPED_SKILL_PREFIXES
            .iter()
            .any(|skipped| name.starts_with(skipped))
        {
            continue;
        }
        if entry.path().is_dir() {
            files.extend(collect(&entry.path(), &format!("{prefix}{name}/"))?);
        } else if name.ends_with(SKILL_FILE_SUFFIX) {
            files.insert(format!("{prefix}{name}"), read_text(&entry.path())?);
        }
    }
    Ok(files)
}

/// `load_packaged_skill_files`: every packaged skill file with its generated marker.
pub(crate) fn packaged_files(root: &Path) -> Result<SkillFiles, WorkspaceError> {
    if !root.join(SKILL_ENTRY_FILE).is_file() {
        return Err(WorkspaceError::user(
            "C805",
            "packaged SQLBuild skill is missing".to_owned(),
            Some("reinstall SQLBuild or report a packaging issue"),
        ));
    }
    Ok(collect(root, "")?
        .into_iter()
        .map(|(path, content)| (path, with_marker(content)))
        .collect())
}

fn generated(path: &Path) -> Result<bool, WorkspaceError> {
    let content: String = read_text(path)?;
    Ok(content.contains(GENERATED_MARKER) || content.contains(LEGACY_GENERATED_MARKER))
}

/// `_skill_collisions`: expected paths occupied by files SQLBuild did not generate.
pub(crate) fn collisions(
    skill_dir: &Path,
    files: &SkillFiles,
) -> Result<Vec<PathBuf>, WorkspaceError> {
    let mut found: Vec<PathBuf> = Vec::new();
    for relative in files.keys() {
        let path: PathBuf = skill_dir.join(relative);
        if path.is_file() && !generated(&path)? {
            found.push(path);
        }
    }
    Ok(found)
}

/// `_stale_generated_files`: generated `.md` files no longer shipped.
fn stale_generated(skill_dir: &Path, files: &SkillFiles) -> Result<Vec<PathBuf>, WorkspaceError> {
    if !skill_dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut candidates: Vec<PathBuf> = walk(skill_dir)
        .into_iter()
        .filter(|path| path.to_string_lossy().ends_with(SKILL_FILE_SUFFIX))
        .collect();
    candidates.sort();
    let mut stale: Vec<PathBuf> = Vec::new();
    for path in candidates {
        let relative: String = path
            .strip_prefix(skill_dir)
            .map(|relative| relative.to_string_lossy().into_owned())
            .unwrap_or_default();
        if !files.contains_key(&relative) && generated(&path)? {
            stale.push(path);
        }
    }
    Ok(stale)
}

fn current(path: &Path, content: &str) -> Result<bool, WorkspaceError> {
    Ok(path.is_file() && read_text(path)? == content)
}

/// `_skill_directory_is_stale`.
pub(crate) fn out_of_date(skill_dir: &Path, files: &SkillFiles) -> Result<bool, WorkspaceError> {
    for (relative, content) in files {
        if !current(&skill_dir.join(relative), content)? {
            return Ok(true);
        }
    }
    Ok(!stale_generated(skill_dir, files)?.is_empty())
}

fn refuse(path: &Path) -> WorkspaceError {
    WorkspaceError::user(
        "C806",
        format!(
            "refusing to overwrite non-generated skill file: {}",
            path.display()
        ),
        Some("rerun with --force to replace it"),
    )
}

/// `_skill_collisions` over several install directories: the first collision refuses the install.
pub(crate) fn refuse_collisions(
    skill_dirs: &[PathBuf],
    files: &SkillFiles,
) -> Result<(), WorkspaceError> {
    for skill_dir in skill_dirs {
        if let Some(path) = collisions(skill_dir, files)?.into_iter().next() {
            return Err(refuse(&path));
        }
    }
    Ok(())
}

/// `_install_skill_directory`: write every packaged file, drop unshipped ones and empty directories.
pub(crate) fn install(
    skill_dir: &Path,
    files: &SkillFiles,
    force: bool,
) -> Result<(), WorkspaceError> {
    for (relative, content) in files {
        let path: PathBuf = skill_dir.join(relative);
        if current(&path, content)? {
            continue;
        }
        if path.exists() && !force && !generated(&path)? {
            return Err(refuse(&path));
        }
        write_atomically(&path, content)?;
    }
    for path in stale_generated(skill_dir, files)? {
        fs::remove_file(path)?;
    }
    let mut directories: Vec<PathBuf> = walk(skill_dir)
        .into_iter()
        .filter(|path| path.is_dir())
        .collect();
    directories.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
    for directory in directories {
        if fs::read_dir(&directory)?.next().is_none() {
            fs::remove_dir(&directory)?;
        }
    }
    Ok(())
}
