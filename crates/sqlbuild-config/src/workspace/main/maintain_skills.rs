//! Check or refresh a project's generated skills without changing a command's outcome.

use std::path::{Path, PathBuf};

use crate::workspace::_helpers::skill_files::{
    SkillFiles, collisions, install, out_of_date, packaged_files,
};
use crate::workspace::_helpers::skill_settings::{SkillSettings, install_paths, load_settings};
use crate::workspace::constants::VALID_SKILL_TARGETS;
use crate::workspace::errors::WorkspaceError;

/// `_stale_skill_message`.
fn stale_message(collision_paths: &[PathBuf]) -> String {
    let mut detail: String = String::new();
    if !collision_paths.is_empty() {
        detail.push_str("  Custom files were not overwritten:\n");
        for path in collision_paths {
            detail.push_str(&format!("    {}\n", path.display()));
        }
    }
    format!("SQLBuild skill files are out of date\n{detail}  Run: sqb skills\n")
}

fn installed_targets(project_dir: &Path) -> Vec<String> {
    VALID_SKILL_TARGETS
        .iter()
        .map(|target| (*target).to_owned())
        .filter(|target| {
            install_paths(project_dir, std::slice::from_ref(target), None)
                .first()
                .is_some_and(|path| path.exists())
        })
        .collect()
}

/// `maintain_sqlbuild_skills`: the notice to show, empty when skills are current.
pub fn maintain_skills(project_dir: &Path, skills_root: &Path) -> Result<String, WorkspaceError> {
    let settings: SkillSettings = load_settings(project_dir)?;
    let targets: Vec<String> = if settings.configured {
        settings.targets
    } else {
        installed_targets(project_dir)
    };
    if targets.is_empty() {
        return Ok(String::new());
    }
    let files: SkillFiles = packaged_files(skills_root)?;
    let mut stale: Vec<PathBuf> = Vec::new();
    let mut collided: Vec<PathBuf> = Vec::new();
    for path in install_paths(project_dir, &targets, None) {
        let skill_dir: PathBuf = path.parent().map(Path::to_path_buf).unwrap_or_default();
        let found: Vec<PathBuf> = collisions(&skill_dir, &files)?;
        if !found.is_empty() {
            collided.extend(found);
            continue;
        }
        if out_of_date(&skill_dir, &files)? {
            stale.push(path);
        }
    }
    if settings.auto_update && !stale.is_empty() {
        let mut message: String = "Updated stale SQLBuild skill files:\n".to_owned();
        for path in &stale {
            install(path.parent().unwrap_or(path), &files, false)?;
            message.push_str(&format!("  {}\n", path.display()));
        }
        if !collided.is_empty() {
            message.push_str(&stale_message(&collided));
        }
        return Ok(message);
    }
    if !stale.is_empty() || !collided.is_empty() {
        return Ok(stale_message(&collided));
    }
    Ok(String::new())
}
