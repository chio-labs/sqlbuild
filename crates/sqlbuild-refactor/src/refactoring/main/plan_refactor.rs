//! Plan a model rename, model move, or column rename from compiler facts.

use crate::refactoring::_helpers::column_planning::{column_rename_context, column_rename_parts};
use crate::refactoring::_helpers::model_planning::{model_parts, model_target};
use crate::refactoring::_helpers::scan_context::ScanContext;
use crate::refactoring::_helpers::text_edits::build_plan;
use crate::refactoring::constants::{COLUMN_MANUAL_HELP, MODEL_MANUAL_HELP};
use crate::refactoring::models::{
    RefactorError, RefactorFacts, RefactorOperation, RefactorPlan, RefactorRequest,
};

pub use crate::refactoring::_helpers::model_planning::DeclarationMoveHost;

/// Every edit, manual location and blocker of one refactoring, without touching files.
///
/// `host` works out the declaration files a model move takes along.
pub fn plan_refactor(
    facts: &RefactorFacts,
    request: &RefactorRequest,
    host: &mut DeclarationMoveHost<'_>,
) -> Result<RefactorPlan, RefactorError> {
    let context = ScanContext::for_facts(facts)?;
    if request.operation == RefactorOperation::RenameColumn {
        let column = column_rename_context(facts, request, &context)?;
        let parts = column_rename_parts(&column)?;
        let renamed = parts
            .cascaded
            .iter()
            .map(|model| (model.clone(), column.old.clone(), column.new.clone()))
            .collect();
        return Ok(build_plan(
            request.clone(),
            parts,
            &[],
            renamed,
            Some(COLUMN_MANUAL_HELP),
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
        Vec::new(),
        Some(MODEL_MANUAL_HELP),
    ))
}
