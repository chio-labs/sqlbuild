//! Several model moves planned together against the state after all of them.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::refactoring::_helpers::edits::text_edits::RefactorParts;
use crate::refactoring::_helpers::files::project_files::project_sql_files;
use crate::refactoring::_helpers::planning::declaration_moves::{
    ModelMove, declaration_moves, shared_destinations,
};
use crate::refactoring::_helpers::planning::model_planning::{
    FinalState, ModelTarget, own_model_parts,
};
use crate::refactoring::_helpers::scanning::scan_context::ScanContext;
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{ManualLocation, RefactorFacts, RefactorOperation};
use crate::refactoring::types::{DeclarationMoveHost, UnitTestScopeHost};

/// Edits, blockers and file moves of every target, with declarations placed once for all.
pub(crate) fn batch_parts(
    facts: &RefactorFacts,
    targets: &[ModelTarget<'_>],
    context: &ScanContext,
    (host, test_host): (&DeclarationMoveHost<'_>, &UnitTestScopeHost<'_>),
) -> Result<RefactorParts, RefactorError> {
    let files = project_sql_files(facts);
    let destinations: Vec<String> = targets.iter().map(ModelTarget::destination).collect();
    let mut state = FinalState {
        vacated: targets
            .iter()
            .map(|target| target.source_path.clone())
            .collect(),
        renamed: targets
            .iter()
            .filter(|target| target.request.new_name != target.model.name)
            .map(|target| target.model.name.clone())
            .collect(),
    };
    let moves: Vec<ModelMove<'_>> = targets
        .iter()
        .zip(&destinations)
        .map(|(target, destination)| ModelMove {
            model: &target.model.name,
            source: &target.source_path,
            destination,
        })
        .collect();
    let declaration =
        declaration_moves(Path::new(&facts.project_dir), &moves, &state.vacated, host)?;
    state
        .vacated
        .extend(declaration.moves.iter().map(|(source, _)| source.clone()));
    let mut parts = RefactorParts {
        blocking: batch_conflicts(targets),
        ..RefactorParts::default()
    };
    let (mut collisions, mut test_blocking, mut pending) = (Vec::new(), Vec::new(), Vec::new());
    let mut test_moves: Vec<(String, String)> = Vec::new();
    for target in targets {
        let own = own_model_parts(facts, (&files, context, test_host), target, &state)?;
        parts.edits.extend(own.edits);
        parts.manual.extend(own.manual);
        collisions.extend(own.collisions);
        test_blocking.extend(own.test_blocking);
        pending.extend(own.pending);
        test_moves.extend(own.test_moves);
        parts.notes.extend(own.notes);
    }
    parts.manual.extend(facts.python_locations.iter().cloned());
    parts.blocking.extend(collisions);
    parts.blocking.extend(declaration.blocking);
    parts.blocking.extend(test_blocking);
    parts.blocking.extend(shared_destinations(
        test_moves
            .iter()
            .map(|(source, destination)| (source.as_str(), destination.as_str())),
        |first, second, _| format!("the unit tests {first} and {second} would both move here"),
    ));
    parts.blocking.extend(pending);
    parts.moves = declaration.moves;
    parts.moves.extend(test_moves);
    parts.moves.extend(
        targets
            .iter()
            .zip(destinations)
            .filter(|(target, destination)| *destination != target.source_path)
            .map(|(target, destination)| (target.source_path.clone(), destination)),
    );
    Ok(parts)
}

/// Moves that contradict each other: a model moved twice, a shared file or name, a reused name.
fn batch_conflicts(targets: &[ModelTarget<'_>]) -> Vec<ManualLocation> {
    let mut conflicts: Vec<ManualLocation> = Vec::new();
    let mut moved: BTreeSet<&str> = BTreeSet::new();
    let mut reported: BTreeSet<&str> = BTreeSet::new();
    let mut by_destination: BTreeMap<String, &str> = BTreeMap::new();
    let mut by_name: BTreeMap<String, &str> = BTreeMap::new();
    let given_up: BTreeMap<String, &str> = targets
        .iter()
        .filter(|target| target.request.new_name != target.model.name)
        .map(|target| (target.model.name.to_lowercase(), target.model.name.as_str()))
        .collect();
    for target in targets {
        let model: &str = &target.model.name;
        let is_move: bool = target.request.operation == RefactorOperation::MoveModel;
        let (verb, participle) = if is_move {
            ("move", "moved")
        } else {
            ("rename", "renamed")
        };
        if !moved.insert(model) {
            if reported.insert(model) {
                conflicts.push(conflict(
                    &target.source_path,
                    format!("model:{model} is {participle} more than once in this batch"),
                ));
            }
            continue;
        }
        let destination: String = target.destination();
        if let Some(other) = by_destination.insert(destination.clone(), model)
            && is_move
        {
            conflicts.push(conflict(
                &destination,
                format!("model:{other} and model:{model} both move to {destination}"),
            ));
            continue;
        }
        let name: &str = &target.request.new_name;
        if let Some(other) = given_up
            .get(&name.to_lowercase())
            .filter(|other| **other != model)
        {
            conflicts.push(conflict(
                &destination,
                format!(
                    "model:{model} would take the name model:{other} gives up in this batch; \
                     the old name must stay free for its history, so {verb} them in separate runs"
                ),
            ));
        }
        if let Some(other) = by_name.insert(name.to_lowercase(), model) {
            conflicts.push(conflict(
                &destination,
                format!("model:{other} and model:{model} would both be named {name}"),
            ));
        }
    }
    conflicts
}

fn conflict(path: &str, reason: String) -> ManualLocation {
    ManualLocation {
        path: path.to_owned(),
        line: None,
        column: None,
        reason,
    }
}
