//! Plan a model rename, model move, or column rename from compiler facts.

use crate::refactoring::_helpers::edits::text_edits::build_plan;
use crate::refactoring::_helpers::planning::column_planning::{
    column_rename_context, column_rename_parts,
};
use crate::refactoring::_helpers::planning::model_planning::{model_parts, model_target};
use crate::refactoring::_helpers::scanning::scan_context::ScanContext;
use crate::refactoring::constants::{COLUMN_MANUAL_HELP, MODEL_MANUAL_HELP};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{RefactorFacts, RefactorOperation, RefactorPlan, RefactorRequest};

use crate::refactoring::types::DeclarationMoveHost;

/// Plan one refactoring without touching files; `host` finds declaration-file moves.
pub fn plan_refactor(
    facts: &RefactorFacts,
    request: &RefactorRequest,
    host: &DeclarationMoveHost<'_>,
) -> Result<RefactorPlan, RefactorError> {
    let context = ScanContext::for_facts(facts)?;
    if request.operation == RefactorOperation::RenameColumn {
        let column = column_rename_context(facts, request, &context)?;
        let parts = column_rename_parts(&column)?;
        let renamed: Vec<(String, String, String)> = parts
            .cascaded
            .iter()
            .map(|model| (model.clone(), column.old.clone(), column.new.clone()))
            .collect();
        return Ok(build_plan(
            request.clone(),
            parts,
            &[],
            (renamed, Some(COLUMN_MANUAL_HELP)),
        ));
    }
    let target = model_target(facts, request)?;
    let parts = model_parts(facts, &target, &context, host)?;
    let mut moves = parts.moves.clone();
    let destination = target.destination();
    if destination != target.source_path {
        moves.push((target.source_path.clone(), destination));
    }
    Ok(build_plan(
        target.request,
        parts,
        &moves,
        (Vec::new(), Some(MODEL_MANUAL_HELP)),
    ))
}
