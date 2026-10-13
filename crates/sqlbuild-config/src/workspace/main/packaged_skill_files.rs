//! The packaged skill files as they are installed.

use std::collections::BTreeMap;
use std::path::Path;

use crate::workspace::_helpers::skill_files::packaged_files;
use crate::workspace::errors::WorkspaceError;

/// Every packaged skill file by skill-relative path, with its generated marker.
pub fn packaged_skill_files(
    skills_root: &Path,
) -> Result<BTreeMap<String, String>, WorkspaceError> {
    packaged_files(skills_root)
}
