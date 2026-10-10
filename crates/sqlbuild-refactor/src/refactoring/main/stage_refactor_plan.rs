//! Stage a refactoring plan in a scratch copy of the project.

use std::path::Path;

use crate::refactoring::_helpers::workspace::{
    copy_project_inputs, read_originals, write_staged_changes,
};
use crate::refactoring::models::{RefactorError, RefactorPlan};

pub use crate::refactoring::_helpers::workspace::Originals;

/// Copy the project inputs once, apply the plan there, and return the original texts.
pub fn stage_refactor_plan(
    project_dir: &Path,
    staging_dir: &Path,
    plan: &RefactorPlan,
    copy_inputs: bool,
) -> Result<Originals, RefactorError> {
    if copy_inputs {
        copy_project_inputs(project_dir, staging_dir)?;
    }
    let originals = read_originals(project_dir, &plan.changes)?;
    write_staged_changes(staging_dir, &originals, &plan.changes)?;
    Ok(originals)
}
