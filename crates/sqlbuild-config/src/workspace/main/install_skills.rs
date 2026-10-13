//! `sqb skills`: install the packaged SQLBuild skill for each agent target.

use std::path::{Path, PathBuf};

use crate::workspace::_helpers::skill_files::{
    SkillFiles, install, packaged_files, refuse_collisions,
};
use crate::workspace::_helpers::skill_settings::{
    SkillSettings, default_targets, install_paths, load_settings, normalize_targets,
};
use crate::workspace::errors::WorkspaceError;
use crate::workspace::models::SkillInstallRequest;

fn target_names(request: &SkillInstallRequest) -> Result<Vec<String>, WorkspaceError> {
    if !request.requested_targets.is_empty() {
        return normalize_targets(&request.requested_targets, "--target");
    }
    let settings: SkillSettings = load_settings(&request.project_dir)?;
    if settings.targets.is_empty() {
        return Ok(default_targets());
    }
    Ok(settings.targets)
}

/// `update_sqlbuild_skills`: the `SKILL.md` path written for every target.
pub fn install_skills(request: &SkillInstallRequest) -> Result<Vec<PathBuf>, WorkspaceError> {
    let targets: Vec<String> = target_names(request)?;
    let home: Option<&Path> = request.global_install.then_some(request.home_dir.as_path());
    let paths: Vec<PathBuf> = install_paths(&request.project_dir, &targets, home);
    let files: SkillFiles = packaged_files(&request.skills_root)?;
    let skill_dirs: Vec<PathBuf> = paths
        .iter()
        .map(|path| path.parent().map(Path::to_path_buf).unwrap_or_default())
        .collect();
    if !request.force {
        refuse_collisions(&skill_dirs, &files)?;
    }
    for skill_dir in &skill_dirs {
        install(skill_dir, &files, request.force)?;
    }
    Ok(paths)
}
