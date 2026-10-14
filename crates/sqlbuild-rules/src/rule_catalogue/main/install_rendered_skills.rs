//! Validate and atomically replace every generated skill target.

use crate::errors::{SkillInstallError, SkillInstallErrorKind};
use crate::rule_catalogue::_helpers::staging::{apply, stage};
use crate::rule_catalogue::constants::REPLACEABLE_SKILL_STATES;
use crate::rule_catalogue::models::SkillTarget;

/// Install `content` at every target, refusing foreign content and rolling back on failure.
pub fn install_rendered_skills(
    content: &str,
    targets: &[SkillTarget],
) -> Result<(), SkillInstallError> {
    for target in targets {
        if !REPLACEABLE_SKILL_STATES.contains(&target.state.as_str()) {
            return Err(SkillInstallError {
                kind: SkillInstallErrorKind::Refused,
                message: format!(
                    "refusing to overwrite {} rules skill: {}",
                    target.state,
                    target.path.display()
                ),
                notes: Vec::new(),
            });
        }
    }
    let paths: Vec<std::path::PathBuf> = targets.iter().map(|target| target.path.clone()).collect();
    let staged = stage(&paths, content.as_bytes())?;
    apply(&staged, content.as_bytes())
}
