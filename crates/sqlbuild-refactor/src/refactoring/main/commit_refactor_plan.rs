//! Write a verified refactoring plan into the project.

use std::path::{Path, PathBuf};

use crate::refactoring::_helpers::files::workspace::commit_changes;
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::RefactorPlan;
use crate::refactoring::types::Originals;

/// Write every change, restoring all files if any write fails, and return the written paths.
pub fn commit_refactor_plan(
    project_dir: &Path,
    originals: &Originals,
    plan: &RefactorPlan,
) -> Result<Vec<PathBuf>, RefactorError> {
    commit_changes(project_dir, originals, &plan.changes)
}
