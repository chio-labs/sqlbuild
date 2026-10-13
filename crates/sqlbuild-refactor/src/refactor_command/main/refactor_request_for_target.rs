//! Read the target of `sqb rename` and `sqb mv` the way `sqb lineage` reads targets.

use sqlbuild_analysis::lineage_command::main::resolve_lineage_target::resolve_lineage_target;
use sqlbuild_analysis::lineage_command::models::{LineageKey, LineageTarget};

use crate::refactor_command::constants::{
    COLUMN_TARGET_KIND, COLUMN_TARGET_SEPARATOR, MODEL_RESOURCE_TYPE, MOVE_SCOPE, MOVE_USAGE,
    RENAME_SCOPE, RENAME_USAGE, TARGET_ERROR_CODE,
};
use crate::refactor_command::models::RefactorTargetRequest;
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{RefactorOperation, RefactorRequest};

/// The planner request for a `[kind:]<model>` or `[kind:]<model>.<column>` target.
pub fn refactor_request_for_target(
    request: &RefactorTargetRequest,
    lookup: &dyn Fn(&str) -> Option<LineageKey>,
) -> Result<RefactorRequest, RefactorError> {
    let raw: &str = request.target.trim();
    let target: LineageTarget = resolve_lineage_target(raw, lookup);
    check_target(raw, &target, request.is_move)?;
    let model_name: String = target
        .name
        .split_once(COLUMN_TARGET_SEPARATOR)
        .map_or(target.name.as_str(), |(model, _)| model)
        .to_owned();
    if request.is_move {
        return Ok(RefactorRequest {
            operation: RefactorOperation::MoveModel,
            model_name,
            new_name: String::new(),
            column_name: None,
            destination: Some(request.destination.clone().unwrap_or_default()),
            cascade: false,
        });
    }
    let new_name: String = request
        .new_name
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_owned();
    let Some(column_name) = target.column_name else {
        if request.cascade {
            return Err(RefactorError::input(
                TARGET_ERROR_CODE,
                "--cascade applies to column renames only",
                None,
            ));
        }
        return Ok(RefactorRequest {
            operation: RefactorOperation::RenameModel,
            model_name,
            new_name,
            column_name: None,
            destination: None,
            cascade: false,
        });
    };
    Ok(RefactorRequest {
        operation: RefactorOperation::RenameColumn,
        model_name,
        new_name,
        column_name: Some(column_name),
        destination: None,
        cascade: request.cascade,
    })
}

fn check_target(raw: &str, target: &LineageTarget, is_move: bool) -> Result<(), RefactorError> {
    let verb: &str = if is_move { "move" } else { "rename" };
    let usage: Option<&str> = Some(if is_move { MOVE_USAGE } else { RENAME_USAGE });
    let fail = |message: String| RefactorError::input(TARGET_ERROR_CODE, message, usage);
    if target.name.is_empty() || target.column_name.as_deref() == Some("") {
        return Err(fail(format!("cannot {verb} '{raw}'")));
    }
    if let Some(key) = &target.key {
        if key.resource_type != MODEL_RESOURCE_TYPE {
            let scope: &str = if is_move { MOVE_SCOPE } else { RENAME_SCOPE };
            return Err(fail(format!(
                "cannot {verb} '{raw}': {} is a {}; {scope}",
                key.name, key.resource_type
            )));
        }
        if !target.kind_matches {
            let kind: &str = target.kind.as_deref().unwrap_or_default();
            let found: String = if kind == COLUMN_TARGET_KIND {
                format!(
                    "column: needs <model>.<column>, and {} names a model",
                    key.name
                )
            } else {
                format!("{} is a {}, not a {kind}", key.name, key.resource_type)
            };
            return Err(fail(format!("cannot {verb} '{raw}': {found}")));
        }
    }
    if is_move && target.column_name.is_some() {
        return Err(RefactorError::input(
            TARGET_ERROR_CODE,
            format!("sqb mv moves models; '{raw}' names a column"),
            Some(&format!(
                "rename a column with sqb rename {} <new_name>",
                target.name
            )),
        ));
    }
    Ok(())
}
