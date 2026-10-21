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

/// One model move: its name and its paths before and after.
pub(crate) struct ModelMove<'a> {
    pub(crate) model: &'a str,
    pub(crate) source: &'a str,
    pub(crate) destination: &'a str,
}

/// Declaration file moves and blockers of every model move together; `vacated` paths are free.
pub(crate) fn declaration_moves(
    project_dir: &Path,
    moves: &[ModelMove<'_>],
    vacated: &BTreeSet<String>,
    host: &DeclarationMoveHost<'_>,
) -> Result<DeclarationMoves, RefactorError> {
    let changed: Vec<(String, String)> = moves
        .iter()
        .filter(|item| parent(item.destination) != parent(item.source))
        .map(|item| (item.model.to_owned(), item.destination.to_owned()))
        .collect();
    let Some((_, first_destination)) = changed.first() else {
        return Ok(DeclarationMoves::default());
    };
    let placement: DeclarationPlacement = host(&changed)?;
    let Some(relocated) = &placement.relocated else {
        return Ok(unsettled(first_destination, &placement.diagnostics));
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
        if record.requires_group {
            blocking.push(blocker(
                original,
                format!(
                    "{} must move to {}/, which keeps its files in group folders, but {} is \
                     not in a group; move it into a group folder of its current role first",
                    original.label,
                    parent(&record.path),
                    original.path
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
    blocking.extend(shared_destinations(
        destinations
            .iter()
            .map(|(source, target)| (source.as_str(), target.as_str())),
        |first, second, target| {
            format!("{first} and {second} would both move to {target}; rename one of them first")
        },
    ));
    let targets: BTreeSet<&String> = destinations.values().collect();
    blocking.extend(
        targets
            .into_iter()
            .filter(|path| !vacated.contains(*path) && join(project_dir, path).exists())
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

/// A blocker at each path two `(source, destination)` moves share, worded by `reason`.
pub(crate) fn shared_destinations<'a>(
    moves: impl Iterator<Item = (&'a str, &'a str)>,
    reason: impl Fn(&str, &str, &str) -> String,
) -> Vec<ManualLocation> {
    let mut sources: BTreeMap<&str, &str> = BTreeMap::new();
    let mut shared: Vec<ManualLocation> = Vec::new();
    for (source, destination) in moves {
        if let Some(other) = sources.insert(destination, source) {
            shared.push(ManualLocation {
                path: destination.to_owned(),
                line: None,
                column: None,
                reason: reason(other, source, destination),
            });
        }
    }
    shared
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
