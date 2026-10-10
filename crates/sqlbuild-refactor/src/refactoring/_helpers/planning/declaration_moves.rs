//! Declaration files a cross-folder model move takes along, as `model_planning.py` worked out.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::refactoring::_helpers::files::paths::{join, parent};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{
    DeclarationMoves, DeclarationPlacement, ManualLocation, PlacedDeclaration,
};
use crate::refactoring::types::DeclarationMoveHost;

const UNSETTLED_REASON: &str = "declaration placement at the destination could not be worked out";

/// The declaration file moves of moving `model` from `source` to `destination`, and blockers.
pub(crate) fn declaration_moves(
    project_dir: &Path,
    model: &str,
    paths: (&str, &str),
    host: &DeclarationMoveHost<'_>,
) -> Result<DeclarationMoves, RefactorError> {
    let (source, destination) = paths;
    if parent(destination) == parent(source) {
        return Ok(DeclarationMoves::default());
    }
    let placement: DeclarationPlacement = host(model, destination)?;
    let Some(relocated) = &placement.relocated else {
        return Ok(unsettled(destination, &placement.diagnostics));
    };
    let mut destinations: BTreeMap<String, String> = BTreeMap::new();
    let mut blocking: Vec<ManualLocation> = Vec::new();
    for record in relocated {
        let Some(original) = placement
            .declarations
            .iter()
            .find(|item| item.key == record.key)
        else {
            continue;
        };
        if !join(project_dir, &original.path).is_file() {
            blocking.push(blocker(
                original,
                format!(
                    "{} must move to {}, but it is not an authored project file",
                    original.label, record.path
                ),
            ));
            continue;
        }
        let planned: &String = destinations
            .entry(original.path.clone())
            .or_insert_with(|| record.path.clone());
        if *planned != record.path {
            let reason = format!(
                "{} holds declarations that must move to different folders ({planned}, {}); \
                 split the file first",
                original.path, record.path
            );
            blocking.push(blocker(original, reason));
        }
    }
    let moving: BTreeSet<&str> = relocated.iter().map(|item| item.key.as_str()).collect();
    for staying in &placement.declarations {
        if let Some(target) = destinations.get(&staying.path)
            && !moving.contains(staying.key.as_str())
        {
            blocking.push(blocker(
                staying,
                format!(
                    "{target} would take {} along, which must stay in {}; split the file first",
                    staying.label, staying.path
                ),
            ));
        }
    }
    let targets: BTreeSet<&String> = destinations.values().collect();
    blocking.extend(
        targets
            .into_iter()
            .filter(|path| join(project_dir, path).exists())
            .map(|path| ManualLocation {
                path: path.clone(),
                line: None,
                column: None,
                reason: "a declaration must move here, but the file already exists".to_owned(),
            }),
    );
    Ok(DeclarationMoves {
        moves: destinations.into_iter().collect(),
        blocking,
    })
}

fn unsettled(destination: &str, diagnostics: &[String]) -> DeclarationMoves {
    let reasons: Vec<String> = if diagnostics.is_empty() {
        vec![UNSETTLED_REASON.to_owned()]
    } else {
        diagnostics.to_vec()
    };
    DeclarationMoves {
        moves: Vec::new(),
        blocking: reasons
            .into_iter()
            .map(|reason| ManualLocation {
                path: destination.to_owned(),
                line: None,
                column: None,
                reason,
            })
            .collect(),
    }
}

fn blocker(record: &PlacedDeclaration, reason: String) -> ManualLocation {
    ManualLocation {
        path: record.path.clone(),
        line: record.line,
        column: record.column,
        reason,
    }
}
