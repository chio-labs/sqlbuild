//! The planner requests of every target of one `sqb rename` or `sqb mv`.

use sqlbuild_analysis::lineage_command::models::LineageKey;

use crate::refactor_command::_helpers::request_for_target::refactor_request_for_target;
use crate::refactor_command::constants::{BATCH_RENAME_USAGE, TARGET_ERROR_CODE};
use crate::refactor_command::models::RefactorTargetRequest;
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{RefactorOperation, RefactorRequest};

/// Each target's request; several renames must all be model renames without `--cascade`.
pub fn refactor_requests(
    targets: &[RefactorTargetRequest],
    lookup: &dyn Fn(&str) -> Option<LineageKey>,
) -> Result<Vec<RefactorRequest>, RefactorError> {
    if targets.len() > 1 && targets.iter().any(|target| target.cascade) {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            "--cascade applies to one column rename, not to several renames",
            Some(BATCH_RENAME_USAGE),
        ));
    }
    let requests: Vec<RefactorRequest> = targets
        .iter()
        .map(|target| refactor_request_for_target(target, lookup))
        .collect::<Result<_, _>>()?;
    if requests.len() <= 1 {
        return Ok(requests);
    }
    if let Some((target, _)) = targets
        .iter()
        .zip(&requests)
        .find(|(_, request)| request.operation == RefactorOperation::RenameColumn)
    {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            format!(
                "'{}' names a column; several renames in one sqb rename must all be models",
                target.target.trim()
            ),
            Some(BATCH_RENAME_USAGE),
        ));
    }
    Ok(requests)
}
